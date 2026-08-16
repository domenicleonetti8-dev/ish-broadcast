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

        if ([cmd isEqualToString:@"start"]) {
            [[BroadcastBridge shared] startBroadcast];
            return size;
        }

        if ([cmd isEqualToString:@"scan"]) {
            [[BroadcastBridge shared] startScan];
            return size;
        }

        if ([cmd isEqualToString:@"scan stop"]) {
            [[BroadcastBridge shared] stopScan];
            return size;
        }

        if ([cmd isEqualToString:@"test"]) {
            NSString *error = nil;
            BOOL ok = [[BroadcastBridge shared]
                playConnectionTest:&error];
            return ok ? (ssize_t)size : _EAGAIN;
        }

        if ([cmd hasPrefix:@"bind "] || [cmd hasPrefix:@"unbind "]) {
            BOOL unbind = [cmd hasPrefix:@"unbind "];
            NSUInteger prefix = unbind ? 7 : 5;
            NSString *identifier = [[cmd substringFromIndex:prefix]
                stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
            NSString *error = nil;
            BOOL ok = unbind
                ? [[BroadcastBridge shared] unbindFinger:identifier error:&error]
                : [[BroadcastBridge shared] bindFinger:identifier error:&error];
            return ok ? (ssize_t)size : _EINVAL;
        }

        if ([cmd hasPrefix:@"advertise"]) {
            NSString *name = [[cmd substringFromIndex:9]
                stringByTrimmingCharactersInSet:
                    NSCharacterSet.whitespaceCharacterSet];

            [[BroadcastBridge shared]
                advertiseName:name.length ? name : @"broadcast"];

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

static int broadcast_audio_open(
    int major, int minor, struct fd *fd
) {
    (void)major;
    (void)minor;
    fd->offset = 0;
    [[BroadcastBridge shared] startBroadcast];
    return 0;
}

static ssize_t broadcast_audio_read(
    struct fd *fd, void *buf, size_t size
) {
    (void)fd;
    (void)buf;
    (void)size;
    return 0;
}

static ssize_t broadcast_audio_write(
    struct fd *fd, const void *buf, size_t size
) {
    (void)fd;
    if (size == 0 || size % 4 != 0)
        return _EINVAL;
    @autoreleasepool {
        NSString *error = nil;
        BOOL ok = [[BroadcastBridge shared]
            writePCM16Stereo:buf length:size error:&error];
        return ok ? (ssize_t)size : _EAGAIN;
    }
}

struct dev_ops broadcast_audio_dev = {
    .open = broadcast_audio_open,
    .fd.read = broadcast_audio_read,
    .fd.write = broadcast_audio_write,
};
