#import <Foundation/Foundation.h>

@interface BroadcastBridge : NSObject
+ (instancetype)shared;
- (void)startBroadcast;
- (void)advertiseName:(NSString *)name;
- (void)stopAdvertising;
- (void)startScan;
- (void)stopScan;
- (BOOL)attachString:(NSString *)identifier error:(NSString **)error;
- (BOOL)detachString:(NSString *)identifier error:(NSString **)error;
- (BOOL)playConnectionTest:(NSString **)error;
- (BOOL)runSignalPathProbe:(NSString **)error;
- (BOOL)writePCM16Stereo:(const void *)bytes
                  length:(NSUInteger)length
                   error:(NSString **)error;
- (NSString *)statusLine;
- (NSDictionary<NSString *, id> *)statusSnapshot;
- (NSString *)diagnosticReport;
@end
