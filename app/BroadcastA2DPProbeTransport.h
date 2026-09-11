#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

// Transport boundary for the product's large `broadcast` bubble. A provider
// must register the classic Bluetooth A2DP Sink profile; BLE/GATT advertising
// does not satisfy this contract.
@protocol BroadcastA2DPProbeTransport <NSObject>
@property (nonatomic, readonly) NSString *providerName;
@property (nonatomic, readonly) BOOL available;
@property (nonatomic, readonly) BOOL registered;
@property (nonatomic, readonly) BOOL findable;
@property (nonatomic, readonly) BOOL connectable;
@property (nonatomic, readonly) NSUInteger inboundSourceConnections;
// Each dictionary must provide id, name, state, attached, active, and evidence.
// `active` is accepted only when `evidence` is exactly
// `native_a2dp_stream`. Every node represents a classic A2DP Source connection.
@property (nonatomic, readonly) NSArray<NSDictionary<NSString *, id> *> *speakerStrings;
@property (nonatomic, readonly) BOOL audioEngineRunning;
@property (nonatomic, readonly) NSUInteger activeSpeakerStrings;
@property (nonatomic, readonly) NSUInteger mappedChannels;
@property (nonatomic, readonly) uint64_t sourceFrames;
@property (nonatomic, readonly) NSUInteger queuedFrames;
- (BOOL)startWithName:(NSString *)name error:(NSError **)error;
- (void)stop;
- (void)startSpeakerDiscovery;
- (void)stopSpeakerDiscovery;
- (BOOL)attachSpeakerString:(NSString *)identifier error:(NSError **)error;
- (BOOL)detachSpeakerString:(NSString *)identifier error:(NSError **)error;
- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSError **)error;
@end

NS_ASSUME_NONNULL_END
