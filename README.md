# broadcast: one speaker probe, ten strings

The product contract is one large classic-Bluetooth speaker probe named exactly
**broadcast**, with up to ten smaller independent speaker strings attached:

`audio source -> broadcast [A2DP Sink] -> strings 1..10 [A2DP Source] -> generic Bluetooth speakers`

The large probe must be registered as an old-school A2DP speaker, findable and
connectable as `broadcast`. Each small string discovers, attaches, streams,
disconnects, and reconnects independently. One string failure must never stop
another. The topology screen renders the large `broadcast` bubble and ten
smaller connected string bubbles; a bubble becomes active only when its native
transport supplies physical-route evidence.

This is a phone-local iSH fork. There is no remote radio, Linux appliance, or
second box in the architecture. iSH controls the native side through
`/dev/broadcast`, and signed 16-bit stereo PCM enters through
`/dev/broadcast_audio` at 48 kHz.

Version 1.6.0 completes the probe contract, ten-string state/failure model,
native transport plug-in seam, bubble topology UI, BLE status control plane,
PCM input, diagnostics, stress tests, and unsigned iPhone build gate. The BLE
service is deliberately separate and advertises only its service UUID; it does
not take the `broadcast` device name or count as classic-speaker registration.

The remaining execution boundary is explicit. Stock iOS public APIs do not let
an app register the classic A2DP Sink/Source profiles. The built-in provider
therefore reports `native_a2dp_provider_unavailable`; it never invents a
findable or connected state. A native environment that can supply those
profiles plugs in as `BroadcastNativeA2DPProbeTransport` without changing the
probe, string, `/dev`, UI, or evidence contract. See
[BROADCAST_TEST.md](BROADCAST_TEST.md) and
[BROADCAST_VERIFICATION.md](BROADCAST_VERIFICATION.md). The provider ABI and
evidence schema are defined in [NATIVE_TRANSPORT.md](NATIVE_TRANSPORT.md).

The App Store and public TestFlight links in the upstream section below install
the original iSH app. They do **not** install this Broadcast fork.

# [iSH upstream](https://ish.app)

[![Build Status](https://github.com/ish-app/ish/actions/workflows/ci.yml/badge.svg)](https://github.com/ish-app/ish/actions)
[![goto counter](https://img.shields.io/github/search/ish-app/ish/goto.svg)](https://github.com/ish-app/ish/search?q=goto)
[![fuck counter](https://img.shields.io/github/search/ish-app/ish/fuck.svg)](https://github.com/ish-app/ish/search?q=fuck)
[![shit counter](https://img.shields.io/github/search/ish-app/ish/shit.svg)](https://github.com/ish-app/ish/search?q=shit)

<p align="center">
<a href="https://ish.app">
<img src="https://ish.app/assets/github-readme.png">
</a>
</p>

A project to get a Linux shell running on iOS, using usermode x86 emulation and syscall translation.

For the current status of the project, check the issues tab, and the commit logs.

- [Upstream iSH App Store page](https://apps.apple.com/us/app/ish-shell/id1436902243)
- [Upstream iSH TestFlight beta](https://testflight.apple.com/join/97i7KM8O)
- [Discord server](https://discord.gg/HFAXj44)
- [Wiki with help and tutorials](https://github.com/ish-app/ish/wiki)
- [README中文](https://github.com/ish-app/ish/blob/master/README_ZH.md) (如若未能保持最新，请提交PR以更新)

# Hacking

This project has a git submodule, make sure to clone with `--recurse-submodules` or run `git submodule update --init` after cloning.

You'll need these things to build the project:

 - Python 3
   + Meson (`pip3 install meson`)
 - Ninja
 - Clang and LLD (on mac, `brew install llvm`, on linux, `sudo apt install clang lld` or `sudo pacman -S clang lld` or whatever)
 - sqlite3 (this is so common it may already be installed on linux and is definitely already installed on mac. if not, do something like `sudo apt install libsqlite3-dev`)
 - libarchive (`brew install libarchive`, `sudo port install libarchive`, `sudo apt install libarchive-dev`) TODO: bundle this dependency

## Build for iOS

Open the project in Xcode, open iSH.xcconfig, and change `ROOT_BUNDLE_IDENTIFIER` to something unique. You'll also need to update the development team ID in the project (not target!) build settings. Then click Run. There are scripts that should do everything else automatically. If you run into any problems, open an issue and I'll try to help.

## Build command line tool for testing

To set up your environment, cd to the project and run `meson build` to create a build directory in `build`. Then cd to the build directory and run `ninja`.

To set up a self-contained Alpine linux filesystem, download the Alpine minirootfs tarball for i386 from the [Alpine website](https://alpinelinux.org/downloads/) and run `./tools/fakefsify`, with the minirootfs tarball as the first argument and the name of the output directory as the second argument. Then you can run things inside the Alpine filesystem with `./ish -f alpine /bin/sh`, assuming the output directory is called `alpine`. If `tools/fakefsify` doesn't exist for you in your build directory, that might be because it couldn't find libarchive on your system (see above for ways to install it.)

You can replace `ish` with `tools/ptraceomatic` to run the program in a real process and single step and compare the registers at each step. I use it for debugging. Requires 64-bit Linux 4.11 or later.

## Logging

iSH has several logging channels which can be enabled at build time. By default, all of them are disabled. To enable them:

- In Xcode: Set the `ISH_LOG` setting in iSH.xcconfig to a space-separated list of log channels.
- With Meson (command line tool for testing): Run `meson configure -Dlog="<space-separated list of log channels>"`.

Available channels:

- `strace`: The most useful channel, logs the parameters and return value of almost every system call.
- `instr`: Logs every instruction executed by the emulator. This slows things down a lot.
- `verbose`: Debug logs that don't fit into another category.
- Grep for `DEFAULT_CHANNEL` to see if more log channels have been added since this list was updated.

# A note on the interpreter

Possibly the most interesting thing I wrote as part of iSH is the interpreter. It's not quite a JIT since it doesn't target machine code. Instead it generates an array of pointers to functions called gadgets, and each gadget ends with a tailcall to the next function; like the threaded code technique used by some Forth interpreters. The result is a speedup of roughly 3-5x compared to emulation using a simpler switch dispatch.

Unfortunately, I made the decision to write nearly all of the gadgets in assembly language. This was probably a good decision with regards to performance (though I'll never know for sure), but a horrible decision with regards to readability, maintainability, and my sanity. The amount of bullshit I've had to put up with from the compiler/assembler/linker is insane. It's like there's a demon in there that makes sure my code is sufficiently deformed, and if not, makes up stupid reasons why it shouldn't compile. In order to stay sane while writing this code, I've had to ignore best practices in code structure and naming. You'll find macros and variables with such descriptive names as `ss` and `s` and `a`. Assembler macros nested beyond belief. And to top it off, there are almost no comments.

So a warning: Long-term exposure to this code may cause loss of sanity, nightmares about GAS macros and linker errors, or any number of other debilitating side effects. This code is known to the State of California to cause cancer, birth defects, and reproductive harm.
