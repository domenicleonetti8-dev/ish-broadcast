#import <Foundation/Foundation.h>

@interface BroadcastBridge : NSObject
+ (instancetype)shared;
- (void)advertiseName:(NSString *)name;
- (void)stopAdvertising;
- (NSString *)statusLine;
@end
