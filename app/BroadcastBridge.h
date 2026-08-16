#import <Foundation/Foundation.h>

@interface BroadcastBridge : NSObject
+ (instancetype)shared;
- (void)advertiseName:(NSString *)name;
- (void)stopAdvertising;
- (void)startScan;
- (void)stopScan;
- (BOOL)bindFinger:(NSString *)identifier error:(NSString **)error;
- (BOOL)unbindFinger:(NSString *)identifier error:(NSString **)error;
- (NSString *)statusLine;
@end
