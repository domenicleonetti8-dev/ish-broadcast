#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

@interface BroadcastAudioRouter : NSObject

@property (atomic, readonly, getter=isRunning) BOOL running;
@property (atomic, readonly) uint64_t sourceFrames;
@property (atomic, readonly) NSUInteger queuedFrames;
@property (atomic, readonly) NSUInteger mappedChannels;
@property (atomic, copy, readonly) NSString *sessionMode;
@property (atomic) BOOL prefersMultidevice;

- (BOOL)startWithError:(NSError **)error;
- (void)stop;
- (void)setEnabledOutputUIDs:(NSSet<NSString *> *)identifiers;
- (BOOL)rebuildRouteWithError:(NSError **)error;
- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSError **)error;
- (NSArray<NSDictionary<NSString *, id> *> *)outputStatus;

@end

NS_ASSUME_NONNULL_END
