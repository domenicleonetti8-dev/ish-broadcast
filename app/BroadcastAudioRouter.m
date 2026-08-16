#import "BroadcastAudioRouter.h"
#import "BroadcastPCM.h"
#import "BroadcastRouteMap.h"

#import <AVFoundation/AVFoundation.h>
#import <AudioToolbox/AudioToolbox.h>
#include <stdint.h>

static NSString * const BroadcastAudioRouterErrorDomain =
    @"BroadcastAudioRouter";
static const double BroadcastAudioSampleRate = 48000.0;
static const AVAudioChannelCount BroadcastAudioChannelCount = 2;
static const NSUInteger BroadcastAudioBytesPerFrame = 4;
static const NSUInteger BroadcastAudioMaximumQueuedFrames = 96000;

@interface BroadcastAudioRouter ()
@property (nonatomic, strong) AVAudioEngine *engine;
@property (nonatomic, strong) AVAudioPlayerNode *player;
@property (nonatomic, strong) AVAudioFormat *sourceFormat;
@property (nonatomic, copy) NSSet<NSString *> *enabledOutputUIDs;
@property (nonatomic, copy) NSArray<NSDictionary<NSString *, id> *> *outputs;
@property (atomic, readwrite, getter=isRunning) BOOL running;
@property (atomic, readwrite) uint64_t sourceFrames;
@property (atomic, readwrite) NSUInteger queuedFrames;
@property (atomic, readwrite) NSUInteger mappedChannels;
@property (atomic, copy, readwrite) NSString *sessionMode;
@end

@implementation BroadcastAudioRouter

- (instancetype)init {
    self = [super init];
    if (self) {
        _enabledOutputUIDs = [NSSet set];
        _outputs = @[];
        _sessionMode = @"inactive";
        _prefersMultidevice = YES;
    }
    return self;
}

- (NSError *)errorWithCode:(NSInteger)code description:(NSString *)description {
    return [NSError errorWithDomain:BroadcastAudioRouterErrorDomain
                               code:code
                           userInfo:@{NSLocalizedDescriptionKey: description}];
}

- (BOOL)failRouteWithError:(NSError *)routeError
                    output:(NSError **)error
{
    if (error)
        *error = routeError;
    [self stop];
    return NO;
}

- (BOOL)isAtLeastIOS26Point2 {
    NSOperatingSystemVersion required = {
        .majorVersion = 26,
        .minorVersion = 2,
        .patchVersion = 0,
    };
    return [NSProcessInfo.processInfo
        isOperatingSystemAtLeastVersion:required];
}

- (AVAudioSessionMode)dualRouteModeForSession:(AVAudioSession *)session {
    for (AVAudioSessionMode mode in session.availableModes) {
        if ([mode rangeOfString:@"dualroute"
                        options:NSCaseInsensitiveSearch].location != NSNotFound)
            return mode;
    }
    return nil;
}

- (BOOL)configureSession:(NSError **)error {
    AVAudioSession *session = AVAudioSession.sharedInstance;
    NSError *localError = nil;
    BOOL configured = NO;
    if (self.prefersMultidevice && [self isAtLeastIOS26Point2]) {
        AVAudioSessionCategoryOptions options =
            AVAudioSessionCategoryOptionMixWithOthers |
            AVAudioSessionCategoryOptionAllowBluetooth;
        if ([session setCategory:AVAudioSessionCategoryMultiRoute
                            mode:AVAudioSessionModeDefault
                         options:options
                           error:&localError]) {
            AVAudioSessionMode dualRoute =
                [self dualRouteModeForSession:session];
            if (dualRoute && [session setMode:dualRoute error:&localError]) {
                self.sessionMode = @"dualRoute";
                configured = YES;
            }
        }
    }

    if (!configured) {
        if (![session setCategory:AVAudioSessionCategoryPlayback
                             mode:AVAudioSessionModeDefault
                          options:AVAudioSessionCategoryOptionMixWithOthers
                            error:&localError]) {
            if (error) *error = localError;
            return NO;
        }
        self.sessionMode = self.prefersMultidevice
            ? @"singleRouteFallback"
            : @"singleRoute";
    }

    // This is a preference, not a hardware requirement. AVAudioEngine can
    // convert the 48 kHz source if the selected route runs at another rate.
    [session setPreferredSampleRate:BroadcastAudioSampleRate
                              error:nil];
    if (![session setActive:YES error:&localError]) {
        if (error) *error = localError;
        return NO;
    }
    return YES;
}

- (BOOL)startWithError:(NSError **)error {
    if (self.running)
        return YES;
    if (![self configureSession:error])
        return NO;

    self.sourceFormat = [[AVAudioFormat alloc]
        initStandardFormatWithSampleRate:BroadcastAudioSampleRate
                                channels:BroadcastAudioChannelCount];
    if (!self.sourceFormat) {
        return [self failRouteWithError:[self errorWithCode:1
            description:@"pcm_format_unavailable"] output:error];
    }

    self.engine = [AVAudioEngine new];
    self.player = [AVAudioPlayerNode new];
    [self.engine attachNode:self.player];
    [self.engine connect:self.player
                      to:self.engine.mainMixerNode
                  format:self.sourceFormat];
    [self.engine prepare];

    self.running = YES;
    if (![self rebuildRouteWithError:error])
        return NO;
    return YES;
}

- (void)stop {
    self.running = NO;
    [self.player stop];
    [self.engine stop];
    [self.engine reset];
    @synchronized (self) {
        self.queuedFrames = 0;
    }
    self.outputs = @[];
    self.mappedChannels = 0;
    self.sessionMode = @"inactive";
    [AVAudioSession.sharedInstance setActive:NO
                                     options:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation
                                       error:nil];
}

- (void)setEnabledOutputUIDs:(NSSet<NSString *> *)identifiers {
    _enabledOutputUIDs = [identifiers copy] ?: [NSSet set];
}

- (BOOL)rebuildRouteWithError:(NSError **)error {
    if (!self.running)
        return YES;

    AVAudioSession *session = AVAudioSession.sharedInstance;
    NSArray<AVAudioSessionPortDescription *> *ports =
        session.currentRoute.outputs;
    if (ports.count > BROADCAST_ROUTE_MAX_PORTS) {
        return [self failRouteWithError:[self errorWithCode:2
            description:@"too_many_audio_ports"] output:error];
    }

    size_t counts[BROADCAST_ROUTE_MAX_PORTS] = {0};
    bool selected[BROADCAST_ROUTE_MAX_PORTS] = {false};
    size_t channelSum = 0;
    NSMutableArray<NSDictionary<NSString *, id> *> *outputStatus =
        [NSMutableArray arrayWithCapacity:ports.count];

    for (NSUInteger index = 0; index < ports.count; index++) {
        AVAudioSessionPortDescription *port = ports[index];
        NSUInteger channelCount = port.channels.count;
        counts[index] = channelCount;
        selected[index] = [self.enabledOutputUIDs containsObject:port.UID];
        [outputStatus addObject:@{
            @"id": port.UID ?: @"unknown",
            @"name": port.portName ?: @"unknown",
            @"type": port.portType ?: @"unknown",
            @"channels": @(channelCount),
            @"channel_offset": @(channelSum),
            @"enabled": @(selected[index]),
        }];
        channelSum += channelCount;
    }

    NSUInteger channelMapCount = session.maximumOutputNumberOfChannels;
    if (channelMapCount == 0)
        channelMapCount = channelSum;
    if (channelMapCount == 0 ||
        channelMapCount > BROADCAST_ROUTE_MAX_CHANNELS) {
        return [self failRouteWithError:[self errorWithCode:3
            description:@"invalid_output_channel_count"] output:error];
    }

    int32_t channelMap[BROADCAST_ROUTE_MAX_CHANNELS];
    struct broadcast_route_map_result result;
    int mapResult = broadcast_route_map_build(
        counts,
        selected,
        ports.count,
        BroadcastAudioChannelCount,
        channelMap,
        channelMapCount,
        &result
    );
    if (mapResult != BROADCAST_ROUTE_MAP_OK) {
        return [self failRouteWithError:[self errorWithCode:4
            description:@"route_map_failed"] output:error];
    }

    [self.player stop];
    [self.engine stop];
    @synchronized (self) {
        self.queuedFrames = 0;
    }

    BOOL useChannelMap = [self.sessionMode isEqualToString:@"dualRoute"] &&
        ports.count > 1;
    if (useChannelMap) {
        AudioUnit outputAudioUnit = self.engine.outputNode.audioUnit;
        if (!outputAudioUnit) {
            return [self failRouteWithError:[self errorWithCode:5
                description:@"output_audio_unit_unavailable"] output:error];
        }
        OSStatus status = AudioUnitSetProperty(
            outputAudioUnit,
            kAudioOutputUnitProperty_ChannelMap,
            kAudioUnitScope_Output,
            0,
            channelMap,
            (UInt32)(channelMapCount * sizeof(channelMap[0]))
        );
        if (status != noErr) {
            return [self failRouteWithError:[self errorWithCode:status
                description:[NSString stringWithFormat:
                    @"channel_map_failed_%d", (int)status]] output:error];
        }
    }

    NSError *startError = nil;
    [self.engine prepare];
    if (![self.engine startAndReturnError:&startError])
        return [self failRouteWithError:startError output:error];
    [self.player play];
    self.outputs = outputStatus;
    self.mappedChannels = result.mapped_channels;
    return YES;
}

- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSError **)error
{
    if (!self.running || !self.engine.isRunning || !self.player) {
        if (error) *error = [self errorWithCode:6
            description:@"audio_engine_not_running"];
        return NO;
    }
    if ((!bytes && length) || length == 0 ||
        length % BroadcastAudioBytesPerFrame != 0) {
        if (error) *error = [self errorWithCode:7
            description:@"pcm_must_be_s16le_stereo"];
        return NO;
    }

    NSUInteger frameCount = length / BroadcastAudioBytesPerFrame;
    if (frameCount > UINT32_MAX) {
        if (error) *error = [self errorWithCode:8
            description:@"pcm_buffer_too_large"];
        return NO;
    }
    @synchronized (self) {
        if (self.queuedFrames > BroadcastAudioMaximumQueuedFrames ||
            frameCount > BroadcastAudioMaximumQueuedFrames -
                self.queuedFrames) {
            if (error) *error = [self errorWithCode:9
                description:@"audio_queue_full"];
            return NO;
        }
        self.queuedFrames += frameCount;
        self.sourceFrames += frameCount;
    }

    AVAudioPCMBuffer *buffer = [[AVAudioPCMBuffer alloc]
        initWithPCMFormat:self.sourceFormat
            frameCapacity:(AVAudioFrameCount)frameCount];
    float **outputChannels = buffer ? buffer.floatChannelData : NULL;
    if (!buffer || !outputChannels ||
        !outputChannels[0] || !outputChannels[1]) {
        @synchronized (self) {
            self.queuedFrames -= frameCount;
            self.sourceFrames -= frameCount;
        }
        if (error) *error = [self errorWithCode:10
            description:@"pcm_buffer_allocation_failed"];
        return NO;
    }
    buffer.frameLength = (AVAudioFrameCount)frameCount;
    size_t framesWritten = 0;
    int conversion = broadcast_pcm_s16le_stereo_to_float(
        bytes,
        length,
        outputChannels[0],
        outputChannels[1],
        frameCount,
        &framesWritten
    );
    if (conversion != BROADCAST_PCM_OK || framesWritten != frameCount) {
        @synchronized (self) {
            self.queuedFrames -= frameCount;
            self.sourceFrames -= frameCount;
        }
        if (error) *error = [self errorWithCode:11
            description:@"pcm_conversion_failed"];
        return NO;
    }

    __weak BroadcastAudioRouter *weakSelf = self;
    [self.player scheduleBuffer:buffer completionHandler:^{
        BroadcastAudioRouter *strongSelf = weakSelf;
        if (!strongSelf)
            return;
        @synchronized (strongSelf) {
            if (strongSelf.queuedFrames >= frameCount)
                strongSelf.queuedFrames -= frameCount;
            else
                strongSelf.queuedFrames = 0;
        }
    }];
    return YES;
}

- (NSArray<NSDictionary<NSString *, id> *> *)outputStatus {
    return [self.outputs copy];
}

@end
