#import <Foundation/Foundation.h>
#import "BroadcastDevice.h"
#import "BroadcastBridge.h"
#include "kernel/errno.h"

static int broadcast_open(
    int major, int minor, struct fd *fd
) {
    [BroadcastBridge shared];
    fd->offset = 0;
    return 0;
}

static ssize_t broadcast_read(
    struct fd *fd, void *buf, size_t size
) {
    @autoreleasepool {
        NSData *data = [[[BroadcastBridge shared] statusLine]
            dataUsingEncoding:NSUTF8StringEncoding];

        if ((size_t)fd->offset >= data.length)
            return 0;

        size_t remaining = data.length - fd->offset;
        if (size > remaining)
            size = remaining;

        [data getBytes:buf
                range:NSMakeRange(fd->offset, size)];

        fd->offset += size;
        return size;
    }
}

static ssize_t broadcast_write(
    struct fd *fd, const void *buf, size_t size
) {
    @autoreleasepool {
        NSString *cmd = [[NSString alloc]
            initWithBytes:buf
                   length:size
                 encoding:NSUTF8StringEncoding];

        if (!cmd)
            return _EINVAL;

        cmd = [cmd stringByTrimmingCharactersInSet:
            NSCharacterSet.whitespaceAndNewlineCharacterSet];

        if ([cmd isEqualToString:@"stop"]) {
            [[BroadcastBridge shared] stopAdvertising];
            return size;
        }

        if ([cmd hasPrefix:@"advertise"]) {
            NSString *name = [[cmd substringFromIndex:9]
                stringByTrimmingCharactersInSet:
                    NSCharacterSet.whitespaceCharacterSet];

            [[BroadcastBridge shared]
                advertiseName:name.length ? name : @"Broadcast"];

            return size;
        }

        return _EINVAL;
    }
}

struct dev_ops broadcast_dev = {
    .open = broadcast_open,
    .fd.read = broadcast_read,
    .fd.write = broadcast_write,
};
