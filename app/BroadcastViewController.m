#import "BroadcastViewController.h"
#import "BroadcastBridge.h"

#import <math.h>

@interface BroadcastTopologyView : UIView
@property (nonatomic, copy) NSArray<NSDictionary<NSString *, id> *> *nodes;
@property (nonatomic) BOOL probeFindable;
@property (nonatomic) BOOL probeConnected;
@end

@implementation BroadcastTopologyView

- (instancetype)initWithFrame:(CGRect)frame {
    self = [super initWithFrame:frame];
    if (self) {
        self.opaque = NO;
        self.isAccessibilityElement = YES;
        self.accessibilityLabel = @"Broadcast probe with ten speaker strings";
    }
    return self;
}

- (UIColor *)labelColor {
    if (@available(iOS 13, *))
        return UIColor.labelColor;
    return UIColor.blackColor;
}

- (UIColor *)mutedColor {
    if (@available(iOS 13, *))
        return UIColor.secondaryLabelColor;
    return UIColor.grayColor;
}

- (UIColor *)activeColor {
    if (@available(iOS 13, *))
        return UIColor.systemGreenColor;
    return UIColor.greenColor;
}

- (UIColor *)pendingColor {
    if (@available(iOS 13, *))
        return UIColor.systemOrangeColor;
    return UIColor.orangeColor;
}

- (void)setNodes:(NSArray<NSDictionary<NSString *,id> *> *)nodes {
    _nodes = [nodes copy] ?: @[];
    [self setNeedsDisplay];
}

- (void)setProbeFindable:(BOOL)probeFindable {
    _probeFindable = probeFindable;
    [self setNeedsDisplay];
}

- (void)setProbeConnected:(BOOL)probeConnected {
    _probeConnected = probeConnected;
    [self setNeedsDisplay];
}

- (void)drawCenteredText:(NSString *)text
                  center:(CGPoint)center
                    font:(UIFont *)font
                   color:(UIColor *)color
                   width:(CGFloat)width
{
    CGRect bounds = [text boundingRectWithSize:CGSizeMake(width, CGFLOAT_MAX)
                                       options:NSStringDrawingUsesLineFragmentOrigin
                                    attributes:@{NSFontAttributeName: font}
                                       context:nil];
    CGRect rect = CGRectMake(center.x - width / 2.0,
        center.y - ceil(bounds.size.height) / 2.0,
        width, ceil(bounds.size.height));
    NSMutableParagraphStyle *style = [NSMutableParagraphStyle new];
    style.alignment = NSTextAlignmentCenter;
    [text drawInRect:rect withAttributes:@{
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: color,
        NSParagraphStyleAttributeName: style,
    }];
}

- (void)drawRect:(CGRect)rect {
    CGContextRef context = UIGraphicsGetCurrentContext();
    if (!context)
        return;

    CGPoint center = CGPointMake(CGRectGetMidX(rect), CGRectGetMidY(rect));
    CGFloat orbitX = MAX(105.0, CGRectGetWidth(rect) / 2.0 - 34.0);
    CGFloat orbitY = MAX(82.0, CGRectGetHeight(rect) / 2.0 - 30.0);
    CGFloat probeRadius = 57.0;
    CGFloat nodeRadius = 22.0;
    NSUInteger maximumStrings = 10;

    UIColor *muted = [self mutedColor];
    UIColor *active = [self activeColor];
    UIColor *pending = [self pendingColor];
    UIColor *probeColor = self.probeConnected ? active :
        (self.probeFindable ? pending : muted);

    for (NSUInteger index = 0; index < maximumStrings; index++) {
        CGFloat angle = -M_PI_2 + (2.0 * M_PI * index / maximumStrings);
        CGPoint nodeCenter = CGPointMake(
            center.x + cos(angle) * orbitX,
            center.y + sin(angle) * orbitY
        );
        NSDictionary<NSString *, id> *node = index < self.nodes.count
            ? self.nodes[index] : nil;
        BOOL attached = [node[@"string_attached"] boolValue];
        BOOL routed = [node[@"active_route"] boolValue];
        UIColor *nodeColor = routed ? active : (attached ? pending : muted);

        CGContextSetStrokeColorWithColor(context,
            [nodeColor colorWithAlphaComponent:attached ? 0.8 : 0.22].CGColor);
        CGContextSetLineWidth(context, attached ? 2.5 : 1.0);
        CGFloat dash[] = {4.0, 5.0};
        CGContextSetLineDash(context, 0, attached ? NULL : dash,
            attached ? 0 : 2);
        CGPoint edge = CGPointMake(
            center.x + cos(angle) * probeRadius,
            center.y + sin(angle) * probeRadius
        );
        CGPoint nodeEdge = CGPointMake(
            nodeCenter.x - cos(angle) * nodeRadius,
            nodeCenter.y - sin(angle) * nodeRadius
        );
        CGContextMoveToPoint(context, edge.x, edge.y);
        CGContextAddLineToPoint(context, nodeEdge.x, nodeEdge.y);
        CGContextStrokePath(context);
        CGContextSetLineDash(context, 0, NULL, 0);

        CGRect nodeRect = CGRectMake(nodeCenter.x - nodeRadius,
            nodeCenter.y - nodeRadius, nodeRadius * 2, nodeRadius * 2);
        CGContextSetFillColorWithColor(context,
            [nodeColor colorWithAlphaComponent:attached ? 0.2 : 0.06].CGColor);
        CGContextSetStrokeColorWithColor(context, nodeColor.CGColor);
        CGContextSetLineWidth(context, attached ? 2.0 : 1.0);
        CGContextFillEllipseInRect(context, nodeRect);
        CGContextStrokeEllipseInRect(context, nodeRect);

        NSString *nodeLabel = node ? [NSString stringWithFormat:@"%lu",
            (unsigned long)(index + 1)] : @"+";
        [self drawCenteredText:nodeLabel
                        center:nodeCenter
                          font:[UIFont boldSystemFontOfSize:12]
                         color:nodeColor
                         width:nodeRadius * 1.5];
    }

    CGRect probeRect = CGRectMake(center.x - probeRadius,
        center.y - probeRadius, probeRadius * 2, probeRadius * 2);
    CGContextSetFillColorWithColor(context,
        [probeColor colorWithAlphaComponent:0.18].CGColor);
    CGContextSetStrokeColorWithColor(context, probeColor.CGColor);
    CGContextSetLineWidth(context, 4.0);
    CGContextFillEllipseInRect(context, probeRect);
    CGContextStrokeEllipseInRect(context, probeRect);
    [self drawCenteredText:@"broadcast"
                    center:CGPointMake(center.x, center.y - 9.0)
                      font:[UIFont boldSystemFontOfSize:17]
                     color:[self labelColor]
                     width:probeRadius * 1.7];
    [self drawCenteredText:@"A2DP sink"
                    center:CGPointMake(center.x, center.y + 14.0)
                      font:[UIFont systemFontOfSize:10]
                     color:probeColor
                     width:probeRadius * 1.5];

    self.accessibilityValue = [NSString stringWithFormat:
        @"Probe %@; %lu of ten string slots observed",
        self.probeConnected ? @"connected" :
            (self.probeFindable ? @"findable" : @"not registered"),
        (unsigned long)MIN(self.nodes.count, maximumStrings)];
}

@end

@interface BroadcastViewController ()
    <UITableViewDataSource, UITableViewDelegate>
@property (nonatomic, strong) UILabel *summaryLabel;
@property (nonatomic, strong) UILabel *healthLabel;
@property (nonatomic, strong) UILabel *errorLabel;
@property (nonatomic, strong) UIButton *startButton;
@property (nonatomic, strong) UIButton *checkButton;
@property (nonatomic, strong) UIButton *testButton;
@property (nonatomic, strong) BroadcastTopologyView *topologyView;
@property (nonatomic, strong) UITableView *tableView;
@property (nonatomic, copy) NSDictionary<NSString *, id> *snapshot;
@property (nonatomic, copy) NSArray<NSDictionary<NSString *, id> *> *devices;
@property (nonatomic, strong) NSTimer *refreshTimer;
@end

@implementation BroadcastViewController

- (void)viewDidLoad {
    [super viewDidLoad];
    self.title = @"broadcast";
    if (@available(iOS 13, *))
        self.view.backgroundColor = UIColor.systemBackgroundColor;
    else
        self.view.backgroundColor = UIColor.whiteColor;
    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc]
        initWithBarButtonSystemItem:UIBarButtonSystemItemDone
                         target:self
                         action:@selector(close:)];
    self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc]
        initWithBarButtonSystemItem:UIBarButtonSystemItemAction
                         target:self
                         action:@selector(shareReport:)];

    self.summaryLabel = [UILabel new];
    self.summaryLabel.font = [UIFont preferredFontForTextStyle:
        UIFontTextStyleHeadline];
    self.summaryLabel.numberOfLines = 0;

    self.healthLabel = [UILabel new];
    self.healthLabel.font = [UIFont preferredFontForTextStyle:
        UIFontTextStyleSubheadline];
    self.healthLabel.numberOfLines = 0;
    self.healthLabel.accessibilityLabel = @"Broadcast readiness";

    self.errorLabel = [UILabel new];
    self.errorLabel.font = [UIFont preferredFontForTextStyle:
        UIFontTextStyleFootnote];
    if (@available(iOS 13, *))
        self.errorLabel.textColor = UIColor.systemRedColor;
    else
        self.errorLabel.textColor = UIColor.redColor;
    self.errorLabel.numberOfLines = 0;

    self.startButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.startButton setTitle:@"Register Probe" forState:UIControlStateNormal];
    [self.startButton addTarget:self
                         action:@selector(toggleBroadcast:)
               forControlEvents:UIControlEventTouchUpInside];

    self.checkButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.checkButton setTitle:@"Run Check" forState:UIControlStateNormal];
    [self.checkButton addTarget:self
                         action:@selector(runCheck:)
               forControlEvents:UIControlEventTouchUpInside];

    self.testButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.testButton setTitle:@"Test Sound" forState:UIControlStateNormal];
    [self.testButton addTarget:self
                        action:@selector(testSound:)
              forControlEvents:UIControlEventTouchUpInside];

    UIStackView *buttons = [[UIStackView alloc]
        initWithArrangedSubviews:@[
            self.startButton,
            self.checkButton,
            self.testButton,
        ]];
    buttons.axis = UILayoutConstraintAxisHorizontal;
    buttons.spacing = 12;
    buttons.alignment = UIStackViewAlignmentCenter;
    buttons.distribution = UIStackViewDistributionFillEqually;

    self.topologyView = [BroadcastTopologyView new];
    self.topologyView.translatesAutoresizingMaskIntoConstraints = NO;
    [self.topologyView.heightAnchor constraintEqualToConstant:260].active = YES;

    UIStackView *header = [[UIStackView alloc]
        initWithArrangedSubviews:@[
            self.summaryLabel,
            self.healthLabel,
            self.topologyView,
            buttons,
            self.errorLabel,
        ]];
    header.axis = UILayoutConstraintAxisVertical;
    header.spacing = 12;
    header.translatesAutoresizingMaskIntoConstraints = NO;

    self.tableView = [[UITableView alloc]
        initWithFrame:CGRectZero style:UITableViewStyleGrouped];
    self.tableView.translatesAutoresizingMaskIntoConstraints = NO;
    self.tableView.dataSource = self;
    self.tableView.delegate = self;
    self.tableView.accessibilityLabel = @"Broadcast speaker strings";

    [self.view addSubview:header];
    [self.view addSubview:self.tableView];
    UILayoutGuide *safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [header.topAnchor constraintEqualToAnchor:safe.topAnchor
                                         constant:16],
        [header.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor
                                             constant:16],
        [header.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor
                                              constant:-16],
        [self.tableView.topAnchor constraintEqualToAnchor:header.bottomAnchor
                                                 constant:8],
        [self.tableView.leadingAnchor constraintEqualToAnchor:
            self.view.leadingAnchor],
        [self.tableView.trailingAnchor constraintEqualToAnchor:
            self.view.trailingAnchor],
        [self.tableView.bottomAnchor constraintEqualToAnchor:
            self.view.bottomAnchor],
    ]];
    [self refreshStatus];
}

- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    self.refreshTimer = [NSTimer scheduledTimerWithTimeInterval:1.0
        target:self
        selector:@selector(refreshStatus)
        userInfo:nil
        repeats:YES];
}

- (void)viewWillDisappear:(BOOL)animated {
    [self.refreshTimer invalidate];
    self.refreshTimer = nil;
    [super viewWillDisappear:animated];
}

- (void)close:(id)sender {
    (void)sender;
    [self dismissViewControllerAnimated:YES completion:nil];
}

- (void)toggleBroadcast:(id)sender {
    (void)sender;
    BOOL requested = [self.snapshot[@"broadcast_requested"] boolValue];
    if (requested) {
        [[BroadcastBridge shared] stopAdvertising];
    } else {
        [[BroadcastBridge shared] startBroadcast];
    }
    [self refreshStatus];
}

- (void)testSound:(id)sender {
    (void)sender;
    NSString *error = nil;
    if ([[BroadcastBridge shared] playConnectionTest:&error]) {
        [self refreshStatus];
        NSUInteger active = [self.snapshot[@"active_strings"]
            unsignedIntegerValue];
        NSString *message = [NSString stringWithFormat:
            @"Listen for the tone on %lu active %@. Hearing it confirms the audio connection.",
            (unsigned long)active,
            active == 1 ? @"string" : @"strings"];
        UIAlertController *success = [UIAlertController
            alertControllerWithTitle:@"Test sound sent"
                             message:message
                      preferredStyle:UIAlertControllerStyleAlert];
        [success addAction:[UIAlertAction actionWithTitle:@"Heard it"
                                                   style:UIAlertActionStyleDefault
                                                 handler:nil]];
        [success addAction:[UIAlertAction actionWithTitle:@"No sound"
                                                   style:UIAlertActionStyleCancel
                                                 handler:nil]];
        [self presentViewController:success animated:YES completion:nil];
        return;
    }
    UIAlertController *alert = [UIAlertController
        alertControllerWithTitle:@"Test did not play"
                         message:error ?: @"unknown_audio_error"
                  preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"OK"
                                              style:UIAlertActionStyleDefault
                                            handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (NSString *)checkmark:(BOOL)passed label:(NSString *)label {
    return [NSString stringWithFormat:@"%@ %@",
        passed ? @"✓" : @"✗", label];
}

- (void)runCheck:(id)sender {
    (void)sender;
    NSString *probeError = nil;
    BOOL probePassed = [[BroadcastBridge shared]
        runSignalPathProbe:&probeError];
    [self refreshStatus];

    BOOL provider = [self.snapshot[@"probe_provider_available"] boolValue];
    BOOL registered = [self.snapshot[@"probe_registered"] boolValue];
    BOOL findable = [self.snapshot[@"probe_findable"] boolValue] &&
        [self.snapshot[@"probe_connectable"] boolValue];
    BOOL inbound = [self.snapshot[@"probe_connected"] boolValue];
    BOOL engine = [self.snapshot[@"audio_engine_running"] boolValue];
    BOOL route = [self.snapshot[@"active_strings"] unsignedIntegerValue] > 0 &&
        [self.snapshot[@"mapped_channels"] unsignedIntegerValue] > 0;
    BOOL ready = [self.snapshot[@"health_ready"] boolValue] && probePassed;

    NSArray<NSString *> *checks = @[
        [self checkmark:provider label:@"native classic-Bluetooth provider"],
        [self checkmark:registered label:@"broadcast registered as A2DP sink"],
        [self checkmark:findable label:@"probe findable and connectable"],
        [self checkmark:inbound label:@"audio source connected to probe"],
        [self checkmark:engine label:@"fan-out audio engine"],
        [self checkmark:route label:@"physical speaker string route"],
        [self checkmark:probePassed label:@"PCM software signal path"],
    ];
    NSString *action = self.snapshot[@"health_action"] ?: @"Retry the check.";
    NSString *message = [checks componentsJoinedByString:@"\n"];
    message = [message stringByAppendingFormat:
        @"\n\n%@\n\nA BLE name never counts as the classic speaker probe. Physical audio is confirmed only after the A2DP registration evidence and listening test both pass.",
        ready ? @"Software path passed." :
            (probeError.length ? probeError : action)];

    UIAlertController *alert = [UIAlertController
        alertControllerWithTitle:ready
            ? @"Software check passed"
            : @"Setup check"
                         message:message
                  preferredStyle:UIAlertControllerStyleAlert];
    if ([self.snapshot[@"can_run_audio_probe"] boolValue]) {
        __weak BroadcastViewController *weakSelf = self;
        [alert addAction:[UIAlertAction actionWithTitle:@"Test Sound"
                                                   style:UIAlertActionStyleDefault
                                                 handler:^(UIAlertAction *action) {
            (void)action;
            [weakSelf testSound:nil];
        }]];
    }
    [alert addAction:[UIAlertAction actionWithTitle:@"Close"
                                              style:UIAlertActionStyleCancel
                                            handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (void)shareReport:(id)sender {
    (void)sender;
    NSString *report = [[BroadcastBridge shared] diagnosticReport];
    UIActivityViewController *activity = [[UIActivityViewController alloc]
        initWithActivityItems:@[report]
        applicationActivities:nil];
    UIPopoverPresentationController *popover =
        activity.popoverPresentationController;
    if (popover)
        popover.barButtonItem = self.navigationItem.leftBarButtonItem;
    [self presentViewController:activity animated:YES completion:nil];
}

- (void)refreshStatus {
    NSDictionary *snapshot = [[BroadcastBridge shared] statusSnapshot];
    if (![snapshot isKindOfClass:NSDictionary.class])
        return;
    self.snapshot = snapshot;
    NSArray *devices = snapshot[@"string_nodes"];
    self.devices = [devices isKindOfClass:NSArray.class] ? devices : @[];

    BOOL running = [snapshot[@"running"] boolValue];
    BOOL requested = [snapshot[@"broadcast_requested"] boolValue];
    NSUInteger strings = [snapshot[@"strings"] unsignedIntegerValue];
    NSUInteger activeStrings = [snapshot[@"active_strings"]
        unsignedIntegerValue];
    NSUInteger maximum = [snapshot[@"maximum_strings"] unsignedIntegerValue];
    BOOL registered = [snapshot[@"probe_registered"] boolValue];
    BOOL findable = [snapshot[@"probe_findable"] boolValue];
    BOOL connectable = [snapshot[@"probe_connectable"] boolValue];
    BOOL connected = [snapshot[@"probe_connected"] boolValue];
    BOOL healthReady = [snapshot[@"health_ready"] boolValue];
    NSString *healthState = snapshot[@"health_state"] ?: @"invalid";
    NSString *healthAction = snapshot[@"health_action"] ?: @"Run Check.";
    NSString *probeState = connected ? @"connected" :
        ((registered && findable && connectable) ? @"findable" :
            (registered ? @"registered" : @"not registered"));
    self.summaryLabel.text = [NSString stringWithFormat:
        @"broadcast • classic Bluetooth speaker probe\nProbe: %@  •  Strings: %lu active / %lu attached / %lu max",
        probeState,
        (unsigned long)activeStrings,
        (unsigned long)strings,
        (unsigned long)maximum];
    NSString *startTitle = requested ? @"Stop Probe" : @"Register Probe";
    [self.startButton setTitle:startTitle
                      forState:UIControlStateNormal];
    self.testButton.enabled = [snapshot[@"can_run_audio_probe"] boolValue];
    self.healthLabel.text = healthReady
        ? @"Probe and strings evidenced — run the listening test"
        : healthAction;
    if (@available(iOS 13, *)) {
        self.healthLabel.textColor = healthReady
            ? UIColor.systemGreenColor
            : ([healthState isEqualToString:@"stopped"]
                ? UIColor.secondaryLabelColor
                : UIColor.systemOrangeColor);
    } else {
        self.healthLabel.textColor = healthReady
            ? UIColor.greenColor
            : ([healthState isEqualToString:@"stopped"]
                ? UIColor.grayColor
                : UIColor.orangeColor);
    }
    NSDictionary *probe = snapshot[@"probe"];
    id probeError = [probe isKindOfClass:NSDictionary.class]
        ? probe[@"error"] : nil;
    id routeError = snapshot[@"error"];
    if ([probeError isKindOfClass:NSString.class]) {
        self.errorLabel.text =
            @"Stock iOS has no public A2DP-sink registration API. The topology is complete; a native transport provider is the remaining execution boundary.";
    } else if ([routeError isKindOfClass:NSString.class]) {
        self.errorLabel.text = routeError;
    } else if (running && activeStrings == 0) {
        self.errorLabel.text =
            @"The probe is live; attach an independently evidenced speaker string.";
    } else {
        self.errorLabel.text = @"";
    }
    self.topologyView.nodes = self.devices;
    self.topologyView.probeFindable = registered && findable && connectable;
    self.topologyView.probeConnected = connected;
    [self.tableView reloadData];
}

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView {
    (void)tableView;
    return 1;
}

- (NSInteger)tableView:(UITableView *)tableView
 numberOfRowsInSection:(NSInteger)section
{
    (void)tableView;
    (void)section;
    return MAX((NSInteger)self.devices.count, 1);
}

- (NSString *)tableView:(UITableView *)tableView
 titleForHeaderInSection:(NSInteger)section
{
    (void)tableView;
    (void)section;
    return @"Attached Bluetooth speaker strings";
}

- (UITableViewCell *)tableView:(UITableView *)tableView
         cellForRowAtIndexPath:(NSIndexPath *)indexPath
{
    static NSString *identifier = @"BroadcastStringCell";
    UITableViewCell *cell = [tableView
        dequeueReusableCellWithIdentifier:identifier];
    if (!cell)
        cell = [[UITableViewCell alloc]
            initWithStyle:UITableViewCellStyleSubtitle
            reuseIdentifier:identifier];

    if (self.devices.count == 0) {
        cell.textLabel.text = @"No speaker strings observed";
        cell.detailTextLabel.text =
            @"Each real speaker appears here only with transport evidence.";
        cell.accessoryType = UITableViewCellAccessoryNone;
        cell.selectionStyle = UITableViewCellSelectionStyleNone;
        return cell;
    }

    NSDictionary *device = self.devices[indexPath.row];
    cell.textLabel.text = device[@"name"] ?: @"unknown";
    cell.detailTextLabel.text = [NSString stringWithFormat:@"%@ • %@",
        device[@"string_state"] ?: @"unknown",
        [device[@"active_route"] boolValue]
            ? @"physical route evidenced" : @"waiting for evidence"];
    cell.accessoryType = [device[@"string_attached"] boolValue]
        ? UITableViewCellAccessoryCheckmark
        : UITableViewCellAccessoryNone;
    cell.selectionStyle = UITableViewCellSelectionStyleDefault;
    return cell;
}

- (void)tableView:(UITableView *)tableView
 didSelectRowAtIndexPath:(NSIndexPath *)indexPath
{
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    if (indexPath.row >= (NSInteger)self.devices.count)
        return;
    NSDictionary *device = self.devices[indexPath.row];
    NSString *identifier = device[@"id"];
    if (!identifier.length)
        return;
    NSString *error = nil;
    if ([device[@"string_attached"] boolValue])
        [[BroadcastBridge shared] detachString:identifier error:&error];
    else
        [[BroadcastBridge shared] attachString:identifier error:&error];
    [self refreshStatus];
}

@end
