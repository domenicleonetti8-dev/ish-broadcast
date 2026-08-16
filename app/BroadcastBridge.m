#import "BroadcastBridge.h"
#import "BroadcastA2DPProbeTransport.h"
#import "BroadcastFingerTable.h"
#import "BroadcastHealth.h"
#import "BroadcastProbeContract.h"

#import <CoreBluetooth/CoreBluetooth.h>
#import <math.h>

static NSString * const BroadcastSavedFingerIdentifiers =
    @"BroadcastSavedFingerIdentifiers";
static NSString * const BroadcastSavedStringIdentifiers =
    @"BroadcastSavedStringIdentifiers";
static NSString * const BroadcastLogicalName = @"broadcast";
static NSString * const BroadcastControlServiceUUID =
    @"B0ADC0DE-0000-4F1A-9000-000000000001";
static NSString * const BroadcastStatusCharacteristicUUID =
    @"B0ADC0DE-0000-4F1A-9000-000000000002";
static const NSUInteger BroadcastMaximumEvents = 64;

_Static_assert(BROADCAST_MAX_STRINGS == BROADCAST_MAX_FINGERS,
    "probe string contract and internal route table must stay aligned");

// This is the truthful stock-iOS boundary. A separately linked native provider
// may conform to BroadcastA2DPProbeTransport, but CoreBluetooth advertising is
// never counted as registration of the classic A2DP Sink profile.
@interface BroadcastUnavailableA2DPProbeTransport : NSObject
    <BroadcastA2DPProbeTransport>
@end

@implementation BroadcastUnavailableA2DPProbeTransport
- (NSString *)providerName { return @"stock_ios_public_api"; }
- (BOOL)available { return NO; }
- (BOOL)registered { return NO; }
- (BOOL)findable { return NO; }
- (BOOL)connectable { return NO; }
- (NSUInteger)inboundSourceConnections { return 0; }
- (NSArray<NSDictionary<NSString *, id> *> *)speakerStrings { return @[]; }
- (BOOL)audioEngineRunning { return NO; }
- (NSUInteger)activeSpeakerStrings { return 0; }
- (NSUInteger)mappedChannels { return 0; }
- (uint64_t)sourceFrames { return 0; }
- (NSUInteger)queuedFrames { return 0; }
- (BOOL)startWithName:(NSString *)name error:(NSError **)error {
    (void)name;
    if (error) {
        *error = [NSError errorWithDomain:@"BroadcastA2DPProbeTransport"
                                     code:1
                                 userInfo:@{
            NSLocalizedDescriptionKey:
                @"a2dp_sink_provider_unavailable_on_stock_ios",
        }];
    }
    return NO;
}
- (void)stop {}
- (void)startSpeakerDiscovery {}
- (void)stopSpeakerDiscovery {}
- (BOOL)attachSpeakerString:(NSString *)identifier error:(NSError **)error {
    (void)identifier;
    return [self startWithName:BroadcastLogicalName error:error];
}
- (BOOL)detachSpeakerString:(NSString *)identifier error:(NSError **)error {
    (void)identifier;
    return [self startWithName:BroadcastLogicalName error:error];
}
- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSError **)error
{
    (void)bytes;
    (void)length;
    return [self startWithName:BroadcastLogicalName error:error];
}
@end

static id<BroadcastA2DPProbeTransport> BroadcastCreateProbeTransport(void) {
    Class providerClass = NSClassFromString(
        @"BroadcastNativeA2DPProbeTransport"
    );
    if (providerClass) {
        id candidate = [[providerClass alloc] init];
        if ([candidate conformsToProtocol:
            @protocol(BroadcastA2DPProbeTransport)])
            return candidate;
    }
    return [BroadcastUnavailableA2DPProbeTransport new];
}

@interface BroadcastBridge () <CBPeripheralManagerDelegate> {
    struct broadcast_finger_table _fingers;
}
@property (nonatomic, strong) CBPeripheralManager *peripheralManager;
@property (nonatomic, strong) id<BroadcastA2DPProbeTransport> probeTransport;
@property (nonatomic, copy) NSString *name;
@property (nonatomic) BOOL requested;
@property (nonatomic) BOOL routeMonitoring;
@property (nonatomic, copy) NSString *lastError;
@property (nonatomic, copy) NSString *probeTransportError;
@property (nonatomic, strong) CBMutableService *controlService;
@property (nonatomic, strong) CBMutableCharacteristic *statusCharacteristic;
@property (nonatomic, strong) NSMutableDictionary<NSUUID *, NSData *> *statusReads;
@property (nonatomic) BOOL controlServiceReady;
@property (nonatomic, strong) NSMutableArray<NSDictionary<NSString *, id> *> *events;
@property (nonatomic, copy) NSString *lastProbeResult;
@property (nonatomic, strong) NSNumber *lastProbeTimestampMs;
@end

@implementation BroadcastBridge

+ (instancetype)shared {
    static BroadcastBridge *bridge;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        bridge = [BroadcastBridge new];
    });
    return bridge;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _name = BroadcastLogicalName;
        _probeTransport = BroadcastCreateProbeTransport();
        broadcast_fingers_init(&_fingers);
        [self restoreSavedFingerRecords];
        _statusReads = [NSMutableDictionary dictionary];
        _events = [NSMutableArray array];
        _lastProbeResult = @"never";
        _peripheralManager = [[CBPeripheralManager alloc]
            initWithDelegate:self
            queue:dispatch_get_main_queue()
            options:@{
                CBPeripheralManagerOptionShowPowerAlertKey: @YES,
            }];
        [self recordEvent:@"bridge_initialized" detail:nil];
    }
    return self;
}

- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
}

- (uint64_t)nowMilliseconds {
    return (uint64_t)(NSProcessInfo.processInfo.systemUptime * 1000.0);
}

- (NSNumber *)wallClockMilliseconds {
    return @((uint64_t)(NSDate.date.timeIntervalSince1970 * 1000.0));
}

- (void)recordEvent:(NSString *)name detail:(NSString *)detail {
    if (!NSThread.isMainThread) {
        dispatch_async(dispatch_get_main_queue(), ^{
            [self recordEvent:name detail:detail];
        });
        return;
    }
    if (!name.length)
        return;
    NSMutableDictionary<NSString *, id> *event = [@{
        @"event": name,
        @"timestamp_ms": [self wallClockMilliseconds],
    } mutableCopy];
    if (detail.length)
        event[@"detail"] = detail;
    while (self.events.count >= BroadcastMaximumEvents)
        [self.events removeObjectAtIndex:0];
    [self.events addObject:event];
}

- (NSString *)bluetoothStateName {
    switch (self.peripheralManager.state) {
        case CBManagerStateUnknown: return @"unknown";
        case CBManagerStateResetting: return @"resetting";
        case CBManagerStateUnsupported: return @"unsupported";
        case CBManagerStateUnauthorized: return @"unauthorized";
        case CBManagerStatePoweredOff: return @"powered_off";
        case CBManagerStatePoweredOn: return @"powered_on";
    }
    return @"unknown";
}

- (NSString *)messageForFingerResult:(int)result {
    switch (result) {
        case BROADCAST_FINGER_NOT_FOUND: return @"unknown_speaker_string";
        case BROADCAST_FINGER_LIMIT_REACHED: return @"string_limit_reached";
        case BROADCAST_FINGER_TABLE_FULL: return @"speaker_table_full";
        case BROADCAST_FINGER_INVALID: return @"invalid_string_state";
        default: return @"string_operation_failed";
    }
}

- (void)persistWantedFingers {
    NSMutableArray<NSString *> *identifiers = [NSMutableArray array];
    for (size_t i = 0; i < _fingers.count; i++) {
        struct broadcast_finger *finger = &_fingers.devices[i];
        if (finger->wanted)
            [identifiers addObject:
                [NSString stringWithUTF8String:finger->identifier]];
    }
    [NSUserDefaults.standardUserDefaults
        setObject:identifiers
        forKey:BroadcastSavedStringIdentifiers];
}

- (void)restoreSavedFingerRecords {
    NSArray<NSString *> *saved = [NSUserDefaults.standardUserDefaults
        stringArrayForKey:BroadcastSavedStringIdentifiers];
    if (!saved) {
        saved = [NSUserDefaults.standardUserDefaults
            stringArrayForKey:BroadcastSavedFingerIdentifiers];
    }
    for (NSString *identifier in saved) {
        if (!identifier.length)
            continue;
        broadcast_fingers_observe(
            &_fingers, identifier.UTF8String, "saved audio output"
        );
        broadcast_fingers_bind(&_fingers, identifier.UTF8String);
    }
}

- (void)refreshAdvertisement {
    if (!self.requested ||
        self.peripheralManager.state != CBManagerStatePoweredOn ||
        !self.controlServiceReady)
        return;

    [self.peripheralManager stopAdvertising];
    [self.peripheralManager startAdvertising:@{
        CBAdvertisementDataServiceUUIDsKey: @[
            [CBUUID UUIDWithString:BroadcastControlServiceUUID]
        ],
    }];
}

- (void)configureControlService {
    self.controlServiceReady = NO;
    [self.statusReads removeAllObjects];
    [self.peripheralManager removeAllServices];
    CBUUID *statusUUID = [CBUUID
        UUIDWithString:BroadcastStatusCharacteristicUUID];
    self.statusCharacteristic = [[CBMutableCharacteristic alloc]
        initWithType:statusUUID
          properties:CBCharacteristicPropertyRead
               value:nil
         permissions:CBAttributePermissionsReadable];
    self.controlService = [[CBMutableService alloc]
        initWithType:[CBUUID UUIDWithString:BroadcastControlServiceUUID]
             primary:YES];
    self.controlService.characteristics = @[self.statusCharacteristic];
    [self.peripheralManager addService:self.controlService];
}

- (void)advertiseName:(NSString *)name {
    (void)name;
    [self startBroadcast];
}

- (void)startBroadcast {
    void (^start)(void) = ^{
        self.name = BroadcastLogicalName;
        self.requested = YES;
        self.routeMonitoring = YES;
        self.lastError = nil;
        self.probeTransportError = nil;
        [self recordEvent:@"broadcast_start_requested" detail:nil];
        NSError *probeError = nil;
        if (![self.probeTransport startWithName:BroadcastLogicalName
                                          error:&probeError]) {
            self.probeTransportError = probeError.localizedDescription;
            [self recordEvent:@"a2dp_sink_registration_blocked"
                       detail:self.probeTransportError];
        } else {
            [self recordEvent:@"a2dp_sink_registered"
                       detail:self.probeTransport.providerName];
            [self.probeTransport startSpeakerDiscovery];
        }
        [self refreshAdvertisement];

        if (self.probeTransport.registered) {
            [self recordEvent:@"broadcast_started"
                       detail:self.probeTransport.providerName];
        } else {
            [self recordEvent:@"broadcast_start_incomplete"
                       detail:self.probeTransportError];
        }
    };
    if (NSThread.isMainThread)
        start();
    else
        dispatch_sync(dispatch_get_main_queue(), start);
}

- (void)stopAdvertising {
    void (^stop)(void) = ^{
        self.requested = NO;
        self.routeMonitoring = NO;
        [self.peripheralManager stopAdvertising];
        [self.probeTransport stopSpeakerDiscovery];
        [self.probeTransport stop];
        self.probeTransportError = nil;
        [self recordEvent:@"broadcast_stopped" detail:nil];
    };
    if (NSThread.isMainThread)
        stop();
    else
        dispatch_sync(dispatch_get_main_queue(), stop);
}

- (void)startScan {
    void (^start)(void) = ^{
        self.routeMonitoring = YES;
        [self.probeTransport startSpeakerDiscovery];
    };
    if (NSThread.isMainThread)
        start();
    else
        dispatch_sync(dispatch_get_main_queue(), start);
}

- (void)stopScan {
    void (^stop)(void) = ^{
        self.routeMonitoring = NO;
        [self.probeTransport stopSpeakerDiscovery];
    };
    if (NSThread.isMainThread)
        stop();
    else
        dispatch_sync(dispatch_get_main_queue(), stop);
}

- (BOOL)attachString:(NSString *)identifier error:(NSString **)error {
    __block BOOL accepted = NO;
    void (^bind)(void) = ^{
        NSDictionary<NSString *, id> *observed = nil;
        for (NSDictionary<NSString *, id> *node in
             self.probeTransport.speakerStrings) {
            if ([node[@"id"] isEqualToString:identifier]) {
                observed = node;
                break;
            }
        }
        if (!observed) {
            NSError *transportError = nil;
            [self.probeTransport attachSpeakerString:identifier
                                               error:&transportError];
            if (error) {
                *error = transportError.localizedDescription ?:
                    @"speaker_string_not_discovered";
            }
            return;
        }
        NSString *name = observed[@"name"];
        int observeResult = broadcast_fingers_observe(
            &self->_fingers,
            identifier.UTF8String,
            name.length ? name.UTF8String : "generic Bluetooth speaker"
        );
        if (observeResult != BROADCAST_FINGER_OK) {
            if (error) *error = [self messageForFingerResult:observeResult];
            return;
        }
        int result = broadcast_fingers_bind(
            &self->_fingers, identifier.UTF8String
        );
        if (result != BROADCAST_FINGER_OK) {
            if (error) *error = [self messageForFingerResult:result];
            return;
        }
        NSError *transportError = nil;
        if (![self.probeTransport attachSpeakerString:identifier
                                                error:&transportError]) {
            broadcast_fingers_unbind(
                &self->_fingers, identifier.UTF8String
            );
            if (error) {
                *error = transportError.localizedDescription ?:
                    @"speaker_string_attach_failed";
            }
            return;
        }
        [self persistWantedFingers];
        [self recordEvent:@"string_attached" detail:identifier];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        bind();
    else
        dispatch_sync(dispatch_get_main_queue(), bind);
    return accepted;
}

- (BOOL)detachString:(NSString *)identifier error:(NSString **)error {
    __block BOOL accepted = NO;
    void (^unbind)(void) = ^{
        NSError *transportError = nil;
        if (![self.probeTransport detachSpeakerString:identifier
                                                error:&transportError]) {
            if (error) {
                *error = transportError.localizedDescription ?:
                    @"speaker_string_detach_failed";
            }
            return;
        }
        int result = broadcast_fingers_unbind(
            &self->_fingers, identifier.UTF8String
        );
        if (result != BROADCAST_FINGER_OK) {
            if (error) *error = [self messageForFingerResult:result];
            return;
        }
        [self persistWantedFingers];
        [self recordEvent:@"string_detached" detail:identifier];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        unbind();
    else
        dispatch_sync(dispatch_get_main_queue(), unbind);
    return accepted;
}

- (BOOL)playConnectionTest:(NSString **)error {
    __block BOOL accepted = NO;
    void (^play)(void) = ^{
        if (!self.requested || !self.probeTransport.registered) {
            if (error) *error = @"broadcast_not_running";
            return;
        }
        if (self.probeTransport.activeSpeakerStrings == 0 ||
            self.probeTransport.mappedChannels == 0) {
            if (error) *error = @"no_active_speaker_strings";
            return;
        }

        const NSUInteger frames = 36000;
        NSMutableData *tone = [NSMutableData dataWithLength:frames * 4];
        int16_t *samples = tone.mutableBytes;
        for (NSUInteger frame = 0; frame < frames; frame++) {
            double phase = 2.0 * M_PI * 440.0 *
                (double)frame / 48000.0;
            int16_t sample = (int16_t)(sin(phase) * 9000.0);
            samples[frame * 2] = sample;
            samples[frame * 2 + 1] = sample;
        }
        NSError *audioError = nil;
        if (![self.probeTransport writePCM16Stereo:tone.bytes
                                             length:tone.length
                                              error:&audioError]) {
            if (error) *error = audioError.localizedDescription;
            [self recordEvent:@"test_tone_failed"
                       detail:audioError.localizedDescription];
            return;
        }
        [self recordEvent:@"test_tone_queued"
                   detail:[NSString stringWithFormat:@"frames=%lu",
            (unsigned long)frames]];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        play();
    else
        dispatch_sync(dispatch_get_main_queue(), play);
    return accepted;
}

- (BOOL)runSignalPathProbe:(NSString **)error {
    __block BOOL accepted = NO;
    void (^probe)(void) = ^{
        self.lastProbeTimestampMs = [self wallClockMilliseconds];
        if (!self.requested || !self.probeTransport.registered) {
            self.lastProbeResult = @"broadcast_not_running";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }
        if (self.probeTransport.activeSpeakerStrings == 0 ||
            self.probeTransport.mappedChannels == 0) {
            self.lastProbeResult = @"no_active_speaker_strings";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }

        const NSUInteger frames = 480;
        NSData *silence = [NSMutableData dataWithLength:frames * 4];
        if (!silence) {
            self.lastProbeResult = @"probe_buffer_allocation_failed";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }
        NSError *audioError = nil;
        if (![self.probeTransport writePCM16Stereo:silence.bytes
                                             length:silence.length
                                              error:&audioError]) {
            self.lastProbeResult = audioError.localizedDescription ?: @"probe_failed";
            if (error) *error = self.lastProbeResult;
            [self recordEvent:@"signal_probe_failed"
                       detail:self.lastProbeResult];
            return;
        }
        self.lastProbeResult = @"passed";
        [self recordEvent:@"signal_probe_passed"
                   detail:[NSString stringWithFormat:@"frames=%lu",
            (unsigned long)frames]];
        accepted = YES;
    };
    if (NSThread.isMainThread)
        probe();
    else
        dispatch_sync(dispatch_get_main_queue(), probe);
    return accepted;
}

- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSString **)error
{
    __block BOOL written = NO;
    void (^write)(void) = ^{
        if (!self.probeTransport.registered ||
            self.probeTransport.activeSpeakerStrings == 0 ||
            self.probeTransport.mappedChannels == 0) {
            if (error) *error = @"no_active_speaker_strings";
            return;
        }
        NSError *audioError = nil;
        written = [self.probeTransport writePCM16Stereo:bytes
                                                  length:length
                                                   error:&audioError];
        if (!written && error)
            *error = audioError.localizedDescription;
    };
    if (NSThread.isMainThread)
        write();
    else
        dispatch_sync(dispatch_get_main_queue(), write);
    return written;
}

- (void)peripheralManagerDidUpdateState:
    (CBPeripheralManager *)peripheral
{
    [self recordEvent:@"bluetooth_state_changed"
               detail:[self bluetoothStateName]];
    if (peripheral.state == CBManagerStatePoweredOn)
        [self configureControlService];
    else
        self.controlServiceReady = NO;
}

- (void)peripheralManager:(CBPeripheralManager *)peripheral
            didAddService:(CBService *)service
                    error:(NSError *)error
{
    (void)peripheral;
    if (error) {
        self.lastError = error.localizedDescription;
        [self recordEvent:@"control_service_failed"
                   detail:self.lastError];
        return;
    }
    if ([service.UUID isEqual:[CBUUID
        UUIDWithString:BroadcastControlServiceUUID]]) {
        self.controlServiceReady = YES;
        [self recordEvent:@"control_service_ready" detail:nil];
        [self refreshAdvertisement];
    }
}

- (void)peripheralManager:(CBPeripheralManager *)peripheral
    didReceiveReadRequest:(CBATTRequest *)request
{
    if (![request.characteristic.UUID isEqual:[CBUUID
        UUIDWithString:BroadcastStatusCharacteristicUUID]]) {
        [peripheral respondToRequest:request
                         withResult:CBATTErrorAttributeNotFound];
        return;
    }
    NSUUID *centralIdentifier = request.central.identifier;
    NSData *status = self.statusReads[centralIdentifier];
    if (request.offset == 0 || !status) {
        if (self.statusReads.count >= 16)
            [self.statusReads removeAllObjects];
        status = [[self statusLine]
            dataUsingEncoding:NSUTF8StringEncoding];
        if (status)
            self.statusReads[centralIdentifier] = status;
    }
    if (!status) {
        [peripheral respondToRequest:request
                         withResult:CBATTErrorUnlikelyError];
        return;
    }
    if (request.offset > status.length) {
        [peripheral respondToRequest:request
                         withResult:CBATTErrorInvalidOffset];
        return;
    }
    request.value = [status subdataWithRange:NSMakeRange(
        request.offset, status.length - request.offset
    )];
    [peripheral respondToRequest:request withResult:CBATTErrorSuccess];
}

- (void)peripheralManagerDidStartAdvertising:
    (CBPeripheralManager *)peripheral
    error:(NSError *)error
{
    (void)peripheral;
    if (error) {
        self.lastError = error.localizedDescription;
        [self recordEvent:@"advertising_failed"
                   detail:self.lastError];
    } else {
        [self recordEvent:@"advertising_started"
                   detail:@"ble_status_service_only"];
    }
}

- (NSDictionary<NSString *, id> *)statusSnapshot {
    __block NSDictionary<NSString *, id> *snapshot;
    void (^read)(void) = ^{
        NSMutableArray<NSDictionary<NSString *, id> *> *devices =
            [NSMutableArray array];
        NSArray<NSDictionary<NSString *, id> *> *transportStrings =
            self.probeTransport.speakerStrings ?: @[];
        NSUInteger rememberedStrings = 0;
        NSUInteger activeStrings = 0;
        NSUInteger stringCount = MIN(
            transportStrings.count, (NSUInteger)BROADCAST_MAX_STRINGS
        );
        for (NSUInteger index = 0; index < stringCount; index++) {
            NSDictionary<NSString *, id> *transportNode =
                transportStrings[index];
            NSString *identifier = transportNode[@"id"];
            if (![identifier isKindOfClass:NSString.class] ||
                !identifier.length)
                continue;
            NSString *name = transportNode[@"name"];
            if (![name isKindOfClass:NSString.class] || !name.length)
                name = @"generic Bluetooth speaker";
            NSString *state = transportNode[@"state"];
            if (![state isKindOfClass:NSString.class] || !state.length)
                state = @"discovered";
            NSString *evidence = transportNode[@"evidence"];
            if (![evidence isKindOfClass:NSString.class] || !evidence.length)
                evidence = @"none";
            BOOL attached = [transportNode[@"attached"] boolValue];
            BOOL active = [transportNode[@"active"] boolValue] &&
                [evidence isEqualToString:@"native_a2dp_stream"];
            if (attached)
                rememberedStrings++;
            if (attached && active)
                activeStrings++;
            [devices addObject:@{
                @"id": identifier,
                @"name": name,
                @"active_route": @(active),
                @"string_attached": @(attached),
                @"string_state": state,
                @"reconnect_attempts":
                    transportNode[@"reconnect_attempts"] ?: @0,
                @"role": @"a2dp_source",
                @"evidence": evidence,
            }];
        }

        struct broadcast_probe_evidence probeEvidence = {
            .native_a2dp_provider_available =
                self.probeTransport.available,
            .a2dp_sink_registered = self.probeTransport.registered,
            .classic_findable = self.probeTransport.findable,
            .classic_connectable = self.probeTransport.connectable,
            .inbound_source_connections =
                self.probeTransport.inboundSourceConnections,
            .ble_gatt_advertising =
                self.peripheralManager.isAdvertising,
        };
        struct broadcast_probe_result probeResult = {
            .state = BROADCAST_PROBE_INVALID,
        };
        broadcast_probe_evaluate(
            self.requested, &probeEvidence, &probeResult
        );

        struct broadcast_health_input healthInput = {
            .broadcast_requested = self.requested,
            .a2dp_sink_provider_available =
                self.probeTransport.available,
            .a2dp_sink_registered = probeResult.registered,
            .probe_findable = probeResult.findable,
            .probe_connectable = probeResult.connectable,
            .inbound_source_connected = probeResult.connected,
            .audio_engine_running =
                self.probeTransport.audioEngineRunning,
            .remembered_strings = rememberedStrings,
            .active_strings = activeStrings,
            .mapped_channels = self.probeTransport.mappedChannels,
        };
        struct broadcast_health_result health = {
            .state = BROADCAST_HEALTH_INVALID,
        };
        broadcast_health_evaluate(&healthInput, &health);
        NSString *healthState = [NSString stringWithUTF8String:
            broadcast_health_state_name(health.state)];
        NSString *healthAction = [NSString stringWithUTF8String:
            broadcast_health_action(health.state)];

        NSDictionary<NSString *, id> *probe = @{
            @"name": BroadcastLogicalName,
            @"profile": @"classic_bluetooth_a2dp_sink",
            @"state": [NSString stringWithUTF8String:
                broadcast_probe_state_name(probeResult.state)],
            @"provider": self.probeTransport.providerName,
            @"provider_available": @(self.probeTransport.available),
            @"registered": @(probeResult.registered),
            @"findable": @(probeResult.findable),
            @"connectable": @(probeResult.connectable),
            @"inbound_source_connections":
                @(self.probeTransport.inboundSourceConnections),
            @"registration_evidence": probeResult.registered
                ? @"native_a2dp_provider"
                : @"none",
            @"error": self.probeTransportError ?: [NSNull null],
        };
        NSDictionary<NSString *, id> *signalPathProbe = @{
            @"result": self.lastProbeResult ?: @"never",
            @"timestamp_ms": self.lastProbeTimestampMs ?: [NSNull null],
            @"scope": @"software signal path; physical sound requires listening",
        };
        NSDictionary<NSString *, id> *controlPlane = @{
            @"transport": @"ble_gatt",
            @"bluetooth_state": [self bluetoothStateName],
            @"service_ready": @(self.controlServiceReady),
            @"advertising": @(self.peripheralManager.isAdvertising),
            @"service_uuid": BroadcastControlServiceUUID,
            @"status_characteristic_uuid":
                BroadcastStatusCharacteristicUUID,
            @"counts_as_classic_speaker_registration": @NO,
        };
        NSBundle *bundle = NSBundle.mainBundle;

        snapshot = @{
            @"name": BroadcastLogicalName,
            @"contract_version": @2,
            @"topology": @"audio source -> broadcast[A2DP sink] -> string[1..10][A2DP source] -> generic speakers",
            @"captured_at_ms": [self wallClockMilliseconds],
            @"app_version": [bundle objectForInfoDictionaryKey:
                @"CFBundleShortVersionString"] ?: @"unknown",
            @"build": [bundle objectForInfoDictionaryKey:
                @"CFBundleVersion"] ?: @"unknown",
            @"running": @(self.requested &&
                probeResult.registered &&
                probeResult.findable &&
                probeResult.connectable),
            @"broadcast_requested": @(self.requested),
            @"probe": probe,
            @"control_plane": controlPlane,
            @"probe_provider_available":
                @(self.probeTransport.available),
            @"probe_registered": @(probeResult.registered),
            @"probe_findable": @(probeResult.findable),
            @"probe_connectable": @(probeResult.connectable),
            @"probe_connected": @(probeResult.connected),
            @"route_monitoring": @(self.routeMonitoring),
            @"maximum_strings": @(BROADCAST_MAX_STRINGS),
            @"maximum_active_strings": @(BROADCAST_MAX_STRINGS),
            @"route_limit": @"ten independent outbound A2DP source strings",
            @"strings": @(rememberedStrings),
            @"active_strings": @(activeStrings),
            @"string_nodes": devices,
            @"fanout_transport": @"native_a2dp_source_provider",
            @"audio_engine_running":
                @(self.probeTransport.audioEngineRunning),
            @"audio_format": @"s16le stereo 48000Hz",
            @"mapped_channels": @(self.probeTransport.mappedChannels),
            @"queued_frames": @(self.probeTransport.queuedFrames),
            @"source_frames": @(self.probeTransport.sourceFrames),
            @"health_state": healthState,
            @"health_action": healthAction,
            @"health_ready": @(health.ready),
            @"can_run_audio_probe": @(health.can_run_audio_probe),
            @"signal_path_probe": signalPathProbe,
            @"hardware_audio_confirmation": @"required",
            @"events": [self.events copy],
            @"error": self.lastError ?: [NSNull null],
        };
    };

    if (NSThread.isMainThread)
        read();
    else
        dispatch_sync(dispatch_get_main_queue(), read);
    return snapshot ?: @{};
}

- (NSString *)statusLine {
    NSData *json = [NSJSONSerialization
        dataWithJSONObject:[self statusSnapshot] options:0 error:nil];
    NSString *line = json ? [[NSString alloc]
        initWithData:json encoding:NSUTF8StringEncoding] : @"{}";
    return [line stringByAppendingString:@"\n"];
}

- (NSString *)diagnosticReport {
    NSData *json = [NSJSONSerialization
        dataWithJSONObject:[self statusSnapshot]
                   options:NSJSONWritingPrettyPrinted
                     error:nil];
    return json ? [[NSString alloc]
        initWithData:json encoding:NSUTF8StringEncoding] : @"{}";
}

@end
