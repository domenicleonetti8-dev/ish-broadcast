#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERM_JS = ROOT / "app" / "terminal" / "term.js"
TERM_M = ROOT / "app" / "TerminalView.m"


def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f"EIRA_VOICE_PATCH: missing anchor: {label}")
    if text.count(old) != 1:
        raise SystemExit(f"EIRA_VOICE_PATCH: ambiguous anchor: {label}")
    return text.replace(old, new, 1)


js = TERM_JS.read_text(encoding="utf-8")
if "EIRA-SPEAK" not in js:
    old = """let decoder = new TextDecoder();
exports.write = (data) => {
    term.io.writeUTF16(decoder.decode(lib.codec.stringToCodeUnitArray(data)));
    syncProp('applicationCursor', term.keyboard.applicationCursor);
};"""
    new = r"""let decoder = new TextDecoder();
const EIRA_VOICE_PREFIX = '\x1b]777;EIRA-SPEAK;';
let eiraVoicePending = '';

function decodeEiraVoice(payload) {
    const binary = atob(payload);
    const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
    return new TextDecoder('utf-8').decode(bytes);
}

function splitEiraVoice(text) {
    eiraVoicePending += text;
    let visible = '';

    while (true) {
        const start = eiraVoicePending.indexOf(EIRA_VOICE_PREFIX);
        if (start < 0) {
            let keep = 0;
            const maxKeep = Math.min(EIRA_VOICE_PREFIX.length - 1, eiraVoicePending.length);
            for (let n = 1; n <= maxKeep; n++) {
                if (EIRA_VOICE_PREFIX.startsWith(eiraVoicePending.slice(-n)))
                    keep = n;
            }
            visible += eiraVoicePending.slice(0, eiraVoicePending.length - keep);
            eiraVoicePending = eiraVoicePending.slice(eiraVoicePending.length - keep);
            break;
        }

        visible += eiraVoicePending.slice(0, start);
        const end = eiraVoicePending.indexOf('\x07', start + EIRA_VOICE_PREFIX.length);
        if (end < 0) {
            eiraVoicePending = eiraVoicePending.slice(start);
            break;
        }

        const payload = eiraVoicePending.slice(start + EIRA_VOICE_PREFIX.length, end);
        try {
            native.speakEira(decodeEiraVoice(payload));
        } catch (error) {
            console.error('Eira voice decode failed', error);
        }
        eiraVoicePending = eiraVoicePending.slice(end + 1);
    }

    return visible;
}

exports.write = (data) => {
    const decoded = decoder.decode(lib.codec.stringToCodeUnitArray(data));
    const visible = splitEiraVoice(decoded);
    if (visible.length)
        term.io.writeUTF16(visible);
    syncProp('applicationCursor', term.keyboard.applicationCursor);
};"""
    js = replace_once(js, old, new, "term.js exports.write")
    TERM_JS.write_text(js, encoding="utf-8")

m = TERM_M.read_text(encoding="utf-8")
if '#import <AVFoundation/AVFoundation.h>' not in m:
    m = replace_once(
        m,
        '#import "NSObject+SaneKVO.h"\n',
        '#import "NSObject+SaneKVO.h"\n#import <AVFoundation/AVFoundation.h>\n',
        "AVFoundation import",
    )

if "eiraSpeechSynthesizer" not in m:
    m = replace_once(
        m,
        '@property (nonatomic) BOOL terminalFocused;\n',
        '@property (nonatomic) BOOL terminalFocused;\n@property (nonatomic) AVSpeechSynthesizer *eiraSpeechSynthesizer;\n',
        "speech synthesizer property",
    )

old_handlers = 'static NSString *const HANDLERS[] = {@"syncFocus", @"focus", @"newScrollHeight", @"newScrollTop", @"openLink"};'
new_handlers = 'static NSString *const HANDLERS[] = {@"syncFocus", @"focus", @"newScrollHeight", @"newScrollTop", @"openLink", @"speakEira"};'
if '@"speakEira"' not in m:
    m = replace_once(m, old_handlers, new_handlers, "speakEira handler")

if "- (void)speakEiraText:" not in m:
    anchor = '- (void)userContentController:(WKUserContentController *)userContentController didReceiveScriptMessage:(WKScriptMessage *)message {'
    method = r'''- (AVSpeechSynthesisVoice *)bestEiraVoice {
    AVSpeechSynthesisVoice *best = nil;
    for (AVSpeechSynthesisVoice *voice in [AVSpeechSynthesisVoice speechVoices]) {
        if (![voice.language hasPrefix:@"en"])
            continue;
        if (@available(iOS 13.0, *)) {
            if (voice.gender != AVSpeechSynthesisVoiceGenderFemale)
                continue;
        }
        if (best == nil || voice.quality > best.quality)
            best = voice;
    }
    return best ?: [AVSpeechSynthesisVoice voiceWithLanguage:@"en-US"];
}

- (void)speakEiraText:(NSString *)text {
    if (![text isKindOfClass:NSString.class] || text.length == 0)
        return;

    dispatch_async(dispatch_get_main_queue(), ^{
        NSError *audioError = nil;
        AVAudioSession *session = AVAudioSession.sharedInstance;
        [session setCategory:AVAudioSessionCategoryPlayAndRecord
                        mode:AVAudioSessionModeSpokenAudio
                     options:AVAudioSessionCategoryOptionDefaultToSpeaker
                       error:&audioError];
        [session setActive:YES error:&audioError];
        [session overrideOutputAudioPort:AVAudioSessionPortOverrideSpeaker
                                   error:&audioError];

        if (self.eiraSpeechSynthesizer == nil)
            self.eiraSpeechSynthesizer = [AVSpeechSynthesizer new];

        [self.eiraSpeechSynthesizer stopSpeakingAtBoundary:AVSpeechBoundaryImmediate];

        AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:text];
        utterance.voice = [self bestEiraVoice];
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.92;
        utterance.pitchMultiplier = 1.02;
        utterance.volume = 1.0;
        [self.eiraSpeechSynthesizer speakUtterance:utterance];
    });
}

'''
    m = replace_once(m, anchor, method + anchor, "speech methods")

if '[self speakEiraText:message.body];' not in m:
    old = '''    } else if ([message.name isEqualToString:@"openLink"]) {
        [UIApplication openURL:message.body];
    }
}'''
    new = '''    } else if ([message.name isEqualToString:@"openLink"]) {
        [UIApplication openURL:message.body];
    } else if ([message.name isEqualToString:@"speakEira"]) {
        [self speakEiraText:message.body];
    }
}'''
    m = replace_once(m, old, new, "speakEira dispatch")

TERM_M.write_text(m, encoding="utf-8")
print("EIRA_NATIVE_VOICE_PATCH=PASS")
