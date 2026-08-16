#import <Foundation/Foundation.h>

@interface BroadcastBridge : NSObject
+ (instancetype)shared;
- (void)startBroadcast;
- (void)advertiseName:(NSString *)name;
- (void)stopAdvertising;
- (void)startScan;
- (void)stopScan;
- (BOOL)bindFinger:(NSString *)identifier error:(NSString **)error;
- (BOOL)unbindFinger:(NSString *)identifier error:(NSString **)error;
- (BOOL)playConnectionTest:(NSString **)error;
- (BOOL)setMultideviceMode:(BOOL)enabled error:(NSString **)error;
- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSString **)error;
- (NSString *)statusLine;
@end
