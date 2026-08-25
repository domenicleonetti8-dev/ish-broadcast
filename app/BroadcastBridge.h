#import <Foundation/Foundation.h>

@interface BroadcastBridge : NSObject
+ (instancetype)shared;
- (void)advertiseName:(NSString *)name;
- (void)stopAdvertising;
- (void)startMicrophoneToEndpoint:(NSString *)endpoint;
- (void)resumeConfiguredMicrophone;
- (void)stopMicrophone;
- (void)forgetMicrophoneEndpoint;
- (NSString *)statusLine;
@end
