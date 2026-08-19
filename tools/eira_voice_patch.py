#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TERM_JS = ROOT / "app" / "terminal" / "term.js"
TERM_M = ROOT / "app" / "TerminalView.m"
INFO = ROOT / "app" / "Info.plist"


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
const EIRA_PROMPT = 'Dom > ';
let eiraVoicePending = '';
let eiraPromptTail = '';

function decodeEiraVoice(payload) {
    const binary = atob(payload);
    const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
    return new TextDecoder('utf-8').decode(bytes);
}

function observeEiraPrompt(text) {
    eiraPromptTail = (eiraPromptTail + text).slice(-256);
    if (eiraPromptTail.includes(EIRA_PROMPT)) {
        native.eiraReady();
        eiraPromptTail = '';
    }
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
    if (visible.length) {
        term.io.writeUTF16(visible);
        observeEiraPrompt(visible);
    }
    syncProp('applicationCursor', term.keyboard.applicationCursor);
};"""
    js = replace_once(js, old, new, "term.js exports.write")
    TERM_JS.write_text(js, encoding="utf-8")


m = TERM_M.read_text(encoding="utf-8")
if '#import <AVFoundation/AVFoundation.h>' not in m:
    m = replace_once(
        m,
        '#import "NSObject+SaneKVO.h"\n',
        '#import "NSObject+SaneKVO.h"\n#import <AVFoundation/AVFoundation.h>\n#import <Speech/Speech.h>\n',
        "AVFoundation/Speech imports",
    )

if '@interface TerminalView () <AVSpeechSynthesizerDelegate>' not in m:
    m = replace_once(
        m,
        '@interface TerminalView ()\n',
        '@interface TerminalView () <AVSpeechSynthesizerDelegate>\n',
        "TerminalView speech delegate",
    )

if "eiraSpeechSynthesizer" not in m:
    m = replace_once(
        m,
        '@property (nonatomic) BOOL terminalFocused;\n',
        '''@property (nonatomic) BOOL terminalFocused;
@property (nonatomic) AVSpeechSynthesizer *eiraSpeechSynthesizer;
@property (nonatomic) SFSpeechRecognizer *eiraSpeechRecognizer;
@property (nonatomic) SFSpeechAudioBufferRecognitionRequest *eiraRecognitionRequest;
@property (nonatomic) SFSpeechRecognitionTask *eiraRecognitionTask;
@property (nonatomic) AVAudioEngine *eiraAudioEngine;
@property (nonatomic) BOOL eiraVoiceAuthorized;
@property (nonatomic) BOOL eiraReadyForInput;
@property (nonatomic) BOOL eiraSpeaking;
@property (nonatomic) BOOL eiraInputTapInstalled;
@property (nonatomic) NSInteger eiraEndpointGeneration;
@property (nonatomic) NSString *eiraPendingTranscript;
''',
        "Eira voice properties",
    )

old_handlers = 'static NSString *const HANDLERS[] = {@"syncFocus", @"focus", @"newScrollHeight", @"newScrollTop", @"openLink"};'
new_handlers = 'static NSString *const HANDLERS[] = {@"syncFocus", @"focus", @"newScrollHeight", @"newScrollTop", @"openLink", @"speakEira", @"eiraReady"};'
if '@"speakEira"' not in m or '@"eiraReady"' not in m:
    m = replace_once(m, old_handlers, new_handlers, "Eira native message handlers")

if "[self prepareEiraVoiceInput];" not in m:
    old = '''    for (int i = 0; i < sizeof(HANDLERS)/sizeof(HANDLERS[0]); i++) {
        [webView.configuration.userContentController addScriptMessageHandler:handler name:HANDLERS[i]];
    }
    webView.frame = self.bounds;'''
    new = '''    for (int i = 0; i < sizeof(HANDLERS)/sizeof(HANDLERS[0]); i++) {
        [webView.configuration.userContentController addScriptMessageHandler:handler name:HANDLERS[i]];
    }
    [self prepareEiraVoiceInput];
    webView.frame = self.bounds;'''
    m = replace_once(m, old, new, "prepare Eira voice input")

if "- (void)prepareEiraVoiceInput" not in m:
    anchor = '- (void)userContentController:(WKUserContentController *)userContentController didReceiveScriptMessage:(WKScriptMessage *)message {'
    methods = r'''- (AVSpeechSynthesisVoice *)bestEiraVoice {
    AVSpeechSynthesisVoice *best = nil;
    NSInteger bestScore = NSIntegerMin;
    for (AVSpeechSynthesisVoice *voice in [AVSpeechSynthesisVoice speechVoices]) {
        if (![voice.language hasPrefix:@"en"])
            continue;
        if (@available(iOS 13.0, *)) {
            if (voice.gender != AVSpeechSynthesisVoiceGenderFemale)
                continue;
        }

        NSInteger score = (NSInteger) voice.quality * 100;
        if ([voice.language isEqualToString:@"en-US"])
            score += 20;
        if (score > bestScore) {
            best = voice;
            bestScore = score;
        }
    }
    return best ?: [AVSpeechSynthesisVoice voiceWithLanguage:@"en-US"];
}

- (void)stopEiraListening {
    self.eiraEndpointGeneration += 1;
    self.eiraPendingTranscript = nil;

    if (self.eiraRecognitionTask != nil) {
        [self.eiraRecognitionTask cancel];
        self.eiraRecognitionTask = nil;
    }
    if (self.eiraRecognitionRequest != nil) {
        [self.eiraRecognitionRequest endAudio];
        self.eiraRecognitionRequest = nil;
    }

    if (self.eiraInputTapInstalled) {
        [self.eiraAudioEngine.inputNode removeTapOnBus:0];
        self.eiraInputTapInstalled = NO;
    }
    if (self.eiraAudioEngine.isRunning)
        [self.eiraAudioEngine stop];
}

- (void)submitEiraTranscript:(NSString *)transcript {
    NSString *text = [transcript stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (text.length == 0 || !self.eiraReadyForInput || self.eiraSpeaking)
        return;

    self.eiraReadyForInput = NO;
    [self stopEiraListening];

    [self insertText:[text stringByAppendingString:@"\n"]];
}

- (void)armEiraEndpointForTranscript:(NSString *)transcript final:(BOOL)final {
    NSString *text = [transcript stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    if (text.length == 0)
        return;

    self.eiraPendingTranscript = text;
    NSInteger generation = ++self.eiraEndpointGeneration;
    NSTimeInterval delay = final ? 0.05 : 1.05;

    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(delay * NSEC_PER_SEC)),
                   dispatch_get_main_queue(), ^{
        if (generation != self.eiraEndpointGeneration)
            return;
        NSString *pending = self.eiraPendingTranscript;
        self.eiraPendingTranscript = nil;
        if (pending.length != 0)
            [self submitEiraTranscript:pending];
    });
}

- (void)startEiraListening {
    if (!self.eiraVoiceAuthorized || !self.eiraReadyForInput || self.eiraSpeaking)
        return;
    if (self.eiraAudioEngine.isRunning || self.eiraRecognitionTask != nil)
        return;

    AVAudioSession *session = AVAudioSession.sharedInstance;
    NSError *audioError = nil;
    [session setCategory:AVAudioSessionCategoryPlayAndRecord
                    mode:AVAudioSessionModeMeasurement
                 options:AVAudioSessionCategoryOptionDefaultToSpeaker
                   error:&audioError];
    [session setActive:YES error:&audioError];
    if (audioError != nil) {
        NSLog(@"Eira microphone audio session failed: %@", audioError);
        return;
    }

    self.eiraRecognitionRequest = [SFSpeechAudioBufferRecognitionRequest new];
    self.eiraRecognitionRequest.shouldReportPartialResults = YES;
    if (@available(iOS 13.0, *)) {
        if (self.eiraSpeechRecognizer.supportsOnDeviceRecognition)
            self.eiraRecognitionRequest.requiresOnDeviceRecognition = YES;
    }

    AVAudioInputNode *inputNode = self.eiraAudioEngine.inputNode;
    AVAudioFormat *format = [inputNode outputFormatForBus:0];
    __weak typeof(self) weakSelf = self;
    [inputNode installTapOnBus:0
                   bufferSize:1024
                       format:format
                        block:^(AVAudioPCMBuffer *buffer, AVAudioTime *when) {
        [weakSelf.eiraRecognitionRequest appendAudioPCMBuffer:buffer];
    }];
    self.eiraInputTapInstalled = YES;

    [self.eiraAudioEngine prepare];
    if (![self.eiraAudioEngine startAndReturnError:&audioError]) {
        NSLog(@"Eira microphone engine failed: %@", audioError);
        [self stopEiraListening];
        return;
    }

    self.eiraRecognitionTask =
        [self.eiraSpeechRecognizer recognitionTaskWithRequest:self.eiraRecognitionRequest
                                               resultHandler:^(SFSpeechRecognitionResult *result, NSError *error) {
        if (result != nil) {
            NSString *text = result.bestTranscription.formattedString ?: @"";
            BOOL final = result.isFinal;
            dispatch_async(dispatch_get_main_queue(), ^{
                [weakSelf armEiraEndpointForTranscript:text final:final];
            });
        }

        if (error != nil) {
            dispatch_async(dispatch_get_main_queue(), ^{
                BOOL restart = weakSelf.eiraReadyForInput && !weakSelf.eiraSpeaking;
                [weakSelf stopEiraListening];
                if (restart) {
                    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.35 * NSEC_PER_SEC)),
                                   dispatch_get_main_queue(), ^{
                        [weakSelf startEiraListening];
                    });
                }
            });
        }
    }];
}

- (void)prepareEiraVoiceInput {
    if (self.eiraAudioEngine != nil)
        return;

    self.eiraAudioEngine = [AVAudioEngine new];
    self.eiraSpeechRecognizer =
        [[SFSpeechRecognizer alloc] initWithLocale:[NSLocale localeWithLocaleIdentifier:@"en-US"]];
    self.eiraSpeechSynthesizer = [AVSpeechSynthesizer new];
    self.eiraSpeechSynthesizer.delegate = self;

    __weak typeof(self) weakSelf = self;
    [SFSpeechRecognizer requestAuthorization:^(SFSpeechRecognizerAuthorizationStatus speechStatus) {
        [AVAudioSession.sharedInstance requestRecordPermission:^(BOOL micGranted) {
            dispatch_async(dispatch_get_main_queue(), ^{
                weakSelf.eiraVoiceAuthorized =
                    (speechStatus == SFSpeechRecognizerAuthorizationStatusAuthorized && micGranted);
                if (weakSelf.eiraVoiceAuthorized && weakSelf.eiraReadyForInput)
                    [weakSelf startEiraListening];
            });
        }];
    }];
}

- (void)speakEiraText:(NSString *)text {
    if (![text isKindOfClass:NSString.class] || text.length == 0)
        return;

    dispatch_async(dispatch_get_main_queue(), ^{
        self.eiraSpeaking = YES;
        [self stopEiraListening];

        NSError *audioError = nil;
        AVAudioSession *session = AVAudioSession.sharedInstance;
        [session setCategory:AVAudioSessionCategoryPlayAndRecord
                        mode:AVAudioSessionModeSpokenAudio
                     options:AVAudioSessionCategoryOptionDefaultToSpeaker
                       error:&audioError];
        [session setActive:YES error:&audioError];
        [session overrideOutputAudioPort:AVAudioSessionPortOverrideSpeaker error:&audioError];

        [self.eiraSpeechSynthesizer stopSpeakingAtBoundary:AVSpeechBoundaryImmediate];

        AVSpeechUtterance *utterance = [AVSpeechUtterance speechUtteranceWithString:text];
        utterance.voice = [self bestEiraVoice];
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * 0.92;
        utterance.pitchMultiplier = 1.02;
        utterance.volume = 1.0;
        [self.eiraSpeechSynthesizer speakUtterance:utterance];
    });
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
 didFinishSpeechUtterance:(AVSpeechUtterance *)utterance {
    self.eiraSpeaking = NO;
    if (self.eiraReadyForInput)
        [self startEiraListening];
}

- (void)speechSynthesizer:(AVSpeechSynthesizer *)synthesizer
 didCancelSpeechUtterance:(AVSpeechUtterance *)utterance {
    self.eiraSpeaking = NO;
    if (self.eiraReadyForInput)
        [self startEiraListening];
}

'''
    m = replace_once(m, anchor, methods + anchor, "Eira voice methods")

if '[self speakEiraText:message.body];' not in m:
    old = '''    } else if ([message.name isEqualToString:@"openLink"]) {
        [UIApplication openURL:message.body];
    }
}'''
    new = '''    } else if ([message.name isEqualToString:@"openLink"]) {
        [UIApplication openURL:message.body];
    } else if ([message.name isEqualToString:@"speakEira"]) {
        [self speakEiraText:message.body];
    } else if ([message.name isEqualToString:@"eiraReady"]) {
        self.eiraReadyForInput = YES;
        [self startEiraListening];
    }
}'''
    m = replace_once(m, old, new, "Eira native message dispatch")

if "EIRA_TYPED_INPUT_PAUSES_MIC" not in m:
    old = '''- (void)insertText:(NSString *)text {
    self.markedText = nil;
'''
    new = '''- (void)insertText:(NSString *)text {
    // EIRA_TYPED_INPUT_PAUSES_MIC
    if ([text containsString:@"\\n"] || [text containsString:@"\\r"]) {
        self.eiraReadyForInput = NO;
        [self stopEiraListening];
    }
    self.markedText = nil;
'''
    m = replace_once(m, old, new, "typed input microphone pause")

TERM_M.write_text(m, encoding="utf-8")


info = INFO.read_text(encoding="utf-8")
if "<key>NSMicrophoneUsageDescription</key>" not in info:
    old = '''\t<key>NSLocalNetworkUsageDescription</key>
\t<string>This is required for connecting to localhost and using the ping command.</string>
'''
    new = '''\t<key>NSMicrophoneUsageDescription</key>
\t<string>Eira uses the microphone so you can speak naturally instead of typing.</string>
\t<key>NSSpeechRecognitionUsageDescription</key>
\t<string>Eira converts your spoken words into the same conversation input path used by typed text.</string>
\t<key>NSLocalNetworkUsageDescription</key>
\t<string>This is required for connecting to localhost and using the ping command.</string>
'''
    info = replace_once(info, old, new, "voice permission descriptions")
    INFO.write_text(info, encoding="utf-8")


print("EIRA_NATIVE_VOICE_INPUT_OUTPUT_PATCH=PASS")
