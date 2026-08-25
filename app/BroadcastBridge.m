#import "BroadcastBridge.h"
#import <CoreBluetooth/CoreBluetooth.h>
#import <AVFoundation/AVFoundation.h>

static NSString *const EiraMicEndpointDefaultsKey = @"EiraMicEndpoint";

@interface BroadcastBridge () <CBPeripheralManagerDelegate>
@property CBPeripheralManager *manager;
@property NSString *name;
@property BOOL requested;
@property NSString *lastError;

@property AVAudioEngine *audioEngine;
@property AVAudioConverter *audioConverter;
@property AVAudioFormat *micOutputFormat;
@property NSURLSession *micSession;
@property NSMutableData *micPCM;
@property dispatch_queue_t micQueue;
@property NSString *micEndpoint;
@property NSString *lastMicError;
@property BOOL micRunning;
@property BOOL micUploadInFlight;
@property NSUInteger micDroppedChunks;
@end

@implementation BroadcastBridge

+ (instancetype)shared {
    static BroadcastBridge *bridge;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        void (^make)(void) = ^{
            bridge = [BroadcastBridge new];
        };
        if (NSThread.isMainThread) make();
        else dispatch_sync(dispatch_get_main_queue(), make);
    });
    return bridge;
}

- (instancetype)init {
    if (self = [super init]) {
        _name = @"Broadcast";
        _manager = [[CBPeripheralManager alloc]
            initWithDelegate:self
            queue:dispatch_get_main_queue()];
        _micQueue = dispatch_queue_create("app.ish.broadcast.mic", DISPATCH_QUEUE_SERIAL);
        _micPCM = [NSMutableData data];
        _micEndpoint = [NSUserDefaults.standardUserDefaults stringForKey:EiraMicEndpointDefaultsKey];

        NSURLSessionConfiguration *config = NSURLSessionConfiguration.ephemeralSessionConfiguration;
        config.requestCachePolicy = NSURLRequestReloadIgnoringLocalCacheData;
        config.URLCache = nil;
        config.HTTPCookieStorage = nil;
        config.timeoutIntervalForRequest = 15.0;
        config.timeoutIntervalForResource = 20.0;
        if (@available(iOS 11.0, *))
            config.waitsForConnectivity = YES;
        _micSession = [NSURLSession sessionWithConfiguration:config];
    }
    return self;
}

- (void)refresh {
    if (!self.requested ||
        self.manager.state != CBManagerStatePoweredOn)
        return;

    [self.manager stopAdvertising];
    [self.manager startAdvertising:@{
        CBAdvertisementDataLocalNameKey: self.name
    }];
}

- (void)advertiseName:(NSString *)name {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.name = name.length ? name : @"Broadcast";
        self.requested = YES;
        self.lastError = nil;
        [self refresh];
    });
}

- (void)stopAdvertising {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.requested = NO;
        [self.manager stopAdvertising];
    });
}

- (NSURL *)listenURLForEndpoint:(NSString *)endpoint {
    NSString *value = [endpoint stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!value.length)
        return nil;
    if (![value containsString:@"://"])
        value = [@"http://" stringByAppendingString:value];
    while ([value hasSuffix:@"/"])
        value = [value substringToIndex:value.length - 1];
    if (![value hasSuffix:@"/v1/listen"])
        value = [value stringByAppendingString:@"/v1/listen"];
    return [NSURL URLWithString:value];
}

- (NSString *)normalizedEndpoint:(NSString *)endpoint {
    NSURL *url = [self listenURLForEndpoint:endpoint];
    if (!url)
        return nil;

    NSString *value = [endpoint stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (!value.length)
        return nil;
    while ([value hasSuffix:@"/"])
        value = [value substringToIndex:value.length - 1];
    if ([value hasSuffix:@"/v1/listen"])
        value = [value substringToIndex:value.length - @"/v1/listen".length];
    if (![value containsString:@"://"])
        value = [@"http://" stringByAppendingString:value];
    return value;
}

- (void)setMicError:(NSString *)error {
    dispatch_async(dispatch_get_main_queue(), ^{
        self.lastMicError = error;
    });
}

- (void)sendMicPCM:(NSData *)pcm {
    if (!pcm.length || !self.micEndpoint.length)
        return;

    NSURL *url = [self listenURLForEndpoint:self.micEndpoint];
    if (!url) {
        [self setMicError:@"invalid microphone endpoint"];
        return;
    }

    if (self.micUploadInFlight) {
        self.micDroppedChunks += 1;
        return;
    }
    self.micUploadInFlight = YES;

    NSTimeInterval ended = NSDate.date.timeIntervalSince1970;
    NSTimeInterval duration = (NSTimeInterval)pcm.length / (16000.0 * 2.0);
    NSDictionary *body = @{
        @"device_id": @"iphone",
        @"pcm_b64": [pcm base64EncodedStringWithOptions:0],
        @"sample_rate": @16000,
        @"channels": @1,
        @"started_at": @(ended - duration),
        @"ended_at": @(ended),
    };

    NSError *jsonError = nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:body options:0 error:&jsonError];
    if (!json) {
        self.micUploadInFlight = NO;
        [self setMicError:jsonError.localizedDescription ?: @"microphone JSON failed"];
        return;
    }

    NSMutableURLRequest *request = [NSMutableURLRequest requestWithURL:url];
    request.HTTPMethod = @"POST";
    request.HTTPBody = json;
    request.cachePolicy = NSURLRequestReloadIgnoringLocalCacheData;
    [request setValue:@"application/json" forHTTPHeaderField:@"Content-Type"];
    request.timeoutInterval = 15.0;

    __weak typeof(self) weakSelf = self;
    [[self.micSession dataTaskWithRequest:request
        completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
            typeof(self) strongSelf = weakSelf;
            if (!strongSelf)
                return;

            dispatch_async(strongSelf.micQueue, ^{
                strongSelf.micUploadInFlight = NO;
            });

            if (error) {
                [strongSelf setMicError:error.localizedDescription];
                return;
            }

            NSInteger status = [(NSHTTPURLResponse *)response statusCode];
            if (status < 200 || status >= 300) {
                [strongSelf setMicError:[NSString stringWithFormat:@"microphone endpoint HTTP %ld", (long)status]];
                return;
            }
            [strongSelf setMicError:nil];
        }] resume];
}

- (void)appendMicPCM:(NSData *)data {
    if (!data.length)
        return;

    dispatch_async(self.micQueue, ^{
        if (!self.micRunning)
            return;
        [self.micPCM appendData:data];

        // Two seconds of signed 16-bit, 16 kHz, mono PCM.
        const NSUInteger chunkBytes = 16000 * 2 * 2;
        while (self.micPCM.length >= chunkBytes) {
            NSData *chunk = [self.micPCM subdataWithRange:NSMakeRange(0, chunkBytes)];
            [self.micPCM replaceBytesInRange:NSMakeRange(0, chunkBytes) withBytes:NULL length:0];
            [self sendMicPCM:chunk];
        }
    });
}

- (void)stopMicrophoneNow {
    self.micRunning = NO;

    if (self.audioEngine) {
        AVAudioInputNode *input = self.audioEngine.inputNode;
        @try {
            [input removeTapOnBus:0];
        } @catch (__unused NSException *exception) {
        }
        [self.audioEngine stop];
    }

    self.audioEngine = nil;
    self.audioConverter = nil;

    dispatch_async(self.micQueue, ^{
        // Privacy-first stop: discard any partial raw-audio tail.
        [self.micPCM setLength:0];
    });

    [AVAudioSession.sharedInstance
        setActive:NO
        withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation
        error:nil];
}

- (void)beginMicrophoneCapture {
    NSError *error = nil;
    AVAudioSession *session = AVAudioSession.sharedInstance;
    AVAudioSessionCategoryOptions options =
        AVAudioSessionCategoryOptionDefaultToSpeaker |
        AVAudioSessionCategoryOptionMixWithOthers;

    if (![session setCategory:AVAudioSessionCategoryPlayAndRecord
                         mode:AVAudioSessionModeMeasurement
                      options:options
                        error:&error]) {
        self.lastMicError = error.localizedDescription;
        self.micRunning = NO;
        return;
    }

    for (AVAudioSessionPortDescription *input in session.availableInputs) {
        if ([input.portType isEqualToString:AVAudioSessionPortBuiltInMic]) {
            [session setPreferredInput:input error:nil];
            break;
        }
    }

    if (![session setActive:YES error:&error]) {
        self.lastMicError = error.localizedDescription;
        self.micRunning = NO;
        return;
    }

    self.audioEngine = [AVAudioEngine new];
    AVAudioInputNode *input = self.audioEngine.inputNode;
    AVAudioFormat *inputFormat = [input outputFormatForBus:0];
    self.micOutputFormat = [[AVAudioFormat alloc]
        initWithCommonFormat:AVAudioPCMFormatInt16
        sampleRate:16000
        channels:1
        interleaved:YES];
    self.audioConverter = [[AVAudioConverter alloc]
        initFromFormat:inputFormat
        toFormat:self.micOutputFormat];

    if (!self.audioConverter) {
        self.lastMicError = @"unable to create microphone audio converter";
        self.micRunning = NO;
        [session setActive:NO withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation error:nil];
        return;
    }

    __weak typeof(self) weakSelf = self;
    [input installTapOnBus:0
                bufferSize:8192
                    format:inputFormat
                     block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
        typeof(self) strongSelf = weakSelf;
        if (!strongSelf || !strongSelf.micRunning)
            return;

        double ratio = 16000.0 / inputFormat.sampleRate;
        AVAudioFrameCount capacity = (AVAudioFrameCount)ceil(buffer.frameLength * ratio) + 32;
        AVAudioPCMBuffer *converted = [[AVAudioPCMBuffer alloc]
            initWithPCMFormat:strongSelf.micOutputFormat
            frameCapacity:capacity];

        __block BOOL supplied = NO;
        NSError *convertError = nil;
        AVAudioConverterOutputStatus status = [strongSelf.audioConverter
            convertToBuffer:converted
            error:&convertError
            withInputFromBlock:^AVAudioBuffer *(AVAudioPacketCount packets,
                                                 AVAudioConverterInputStatus *inputStatus) {
                if (supplied) {
                    *inputStatus = AVAudioConverterInputStatus_NoDataNow;
                    return nil;
                }
                supplied = YES;
                *inputStatus = AVAudioConverterInputStatus_HaveData;
                return buffer;
            }];

        if (status == AVAudioConverterOutputStatus_Error) {
            [strongSelf setMicError:convertError.localizedDescription ?: @"microphone conversion failed"];
            return;
        }
        if (!converted.frameLength)
            return;

        AudioBuffer audioBuffer = converted.audioBufferList->mBuffers[0];
        if (!audioBuffer.mData || !audioBuffer.mDataByteSize)
            return;
        NSData *pcm = [NSData dataWithBytes:audioBuffer.mData length:audioBuffer.mDataByteSize];
        [strongSelf appendMicPCM:pcm];
    }];

    [self.audioEngine prepare];
    if (![self.audioEngine startAndReturnError:&error]) {
        [input removeTapOnBus:0];
        self.audioEngine = nil;
        self.audioConverter = nil;
        self.lastMicError = error.localizedDescription;
        self.micRunning = NO;
        [session setActive:NO withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation error:nil];
        return;
    }
    self.lastMicError = nil;
}

- (void)startMicrophoneToEndpoint:(NSString *)endpoint {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSString *normalized = [self normalizedEndpoint:endpoint];
        if (!normalized.length) {
            self.lastMicError = @"invalid microphone endpoint";
            return;
        }

        if (self.micRunning || self.audioEngine)
            [self stopMicrophoneNow];

        self.micEndpoint = normalized;
        [NSUserDefaults.standardUserDefaults setObject:normalized forKey:EiraMicEndpointDefaultsKey];
        self.lastMicError = nil;
        self.micDroppedChunks = 0;

        AVAudioSession *session = AVAudioSession.sharedInstance;
        [session requestRecordPermission:^(BOOL granted) {
            dispatch_async(dispatch_get_main_queue(), ^{
                if (!granted) {
                    self.lastMicError = @"microphone permission denied";
                    self.micRunning = NO;
                    return;
                }
                self.micRunning = YES;
                dispatch_sync(self.micQueue, ^{
                    [self.micPCM setLength:0];
                });
                [self beginMicrophoneCapture];
            });
        }];
    });
}

- (void)resumeConfiguredMicrophone {
    dispatch_async(dispatch_get_main_queue(), ^{
        NSString *endpoint = self.micEndpoint;
        if (!endpoint.length || self.micRunning)
            return;
        [self startMicrophoneToEndpoint:endpoint];
    });
}

- (void)stopMicrophone {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self stopMicrophoneNow];
    });
}

- (void)forgetMicrophoneEndpoint {
    dispatch_async(dispatch_get_main_queue(), ^{
        [self stopMicrophoneNow];
        self.micEndpoint = nil;
        [NSUserDefaults.standardUserDefaults removeObjectForKey:EiraMicEndpointDefaultsKey];
        self.lastMicError = nil;
    });
}

- (void)peripheralManagerDidUpdateState:
    (CBPeripheralManager *)peripheral
{
    [self refresh];
}

- (void)peripheralManagerDidStartAdvertising:
    (CBPeripheralManager *)peripheral
    error:(NSError *)error
{
    self.lastError = error.localizedDescription;
}

- (NSString *)statusLine {
    __block NSString *line;

    void (^read)(void) = ^{
        line = [NSString stringWithFormat:
            @"state=%ld advertising=%d name=%@ error=%@ mic=%d mic_configured=%d mic_endpoint=%@ mic_error=%@ mic_dropped_chunks=%lu\n",
            (long)self.manager.state,
            self.manager.isAdvertising,
            self.name,
            self.lastError ?: @"none",
            self.micRunning,
            self.micEndpoint.length > 0,
            self.micEndpoint ?: @"none",
            self.lastMicError ?: @"none",
            (unsigned long)self.micDroppedChunks];
    };

    if (NSThread.isMainThread)
        read();
    else
        dispatch_sync(dispatch_get_main_queue(), read);

    return line;
}

@end
