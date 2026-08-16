#import "BroadcastViewController.h"
#import "BroadcastBridge.h"

#import <AVKit/AVKit.h>

@interface BroadcastViewController ()
    <UITableViewDataSource, UITableViewDelegate>
@property (nonatomic, strong) UILabel *summaryLabel;
@property (nonatomic, strong) UILabel *errorLabel;
@property (nonatomic, strong) UIButton *startButton;
@property (nonatomic, strong) UIButton *testButton;
@property (nonatomic, strong) UISegmentedControl *modeControl;
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

    self.summaryLabel = [UILabel new];
    self.summaryLabel.font = [UIFont preferredFontForTextStyle:
        UIFontTextStyleHeadline];
    self.summaryLabel.numberOfLines = 0;

    self.errorLabel = [UILabel new];
    self.errorLabel.font = [UIFont preferredFontForTextStyle:
        UIFontTextStyleFootnote];
    if (@available(iOS 13, *))
        self.errorLabel.textColor = UIColor.systemRedColor;
    else
        self.errorLabel.textColor = UIColor.redColor;
    self.errorLabel.numberOfLines = 0;

    self.startButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.startButton addTarget:self
                         action:@selector(toggleBroadcast:)
               forControlEvents:UIControlEventTouchUpInside];

    self.testButton = [UIButton buttonWithType:UIButtonTypeSystem];
    [self.testButton setTitle:@"Test Sound" forState:UIControlStateNormal];
    [self.testButton addTarget:self
                        action:@selector(testSound:)
              forControlEvents:UIControlEventTouchUpInside];

    AVRoutePickerView *routePicker = [AVRoutePickerView new];
    routePicker.activeTintColor = UIColor.systemGreenColor;
    routePicker.tintColor = UIColor.systemBlueColor;
    routePicker.accessibilityLabel = @"Choose Bluetooth audio output";
    [routePicker.widthAnchor constraintEqualToConstant:44].active = YES;
    [routePicker.heightAnchor constraintEqualToConstant:44].active = YES;

    UILabel *routeLabel = [UILabel new];
    routeLabel.text = @"Choose Audio";
    routeLabel.font = [UIFont preferredFontForTextStyle:
        UIFontTextStyleFootnote];

    UIStackView *routeControl = [[UIStackView alloc]
        initWithArrangedSubviews:@[routePicker, routeLabel]];
    routeControl.axis = UILayoutConstraintAxisHorizontal;
    routeControl.spacing = 8;
    routeControl.alignment = UIStackViewAlignmentCenter;

    UIStackView *buttons = [[UIStackView alloc]
        initWithArrangedSubviews:@[self.startButton, self.testButton]];
    buttons.axis = UILayoutConstraintAxisHorizontal;
    buttons.spacing = 12;
    buttons.alignment = UIStackViewAlignmentCenter;
    buttons.distribution = UIStackViewDistributionFillEqually;

    self.modeControl = [[UISegmentedControl alloc]
        initWithItems:@[@"Multi", @"Compatible"]];
    self.modeControl.accessibilityLabel = @"Audio routing mode";
    [self.modeControl addTarget:self
                         action:@selector(changeMode:)
               forControlEvents:UIControlEventValueChanged];

    UIStackView *header = [[UIStackView alloc]
        initWithArrangedSubviews:@[
            self.summaryLabel,
            self.modeControl,
            buttons,
            routeControl,
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
    self.tableView.accessibilityLabel = @"Broadcast fingers";

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
    BOOL running = [self.snapshot[@"running"] boolValue];
    if (requested && running) {
        [[BroadcastBridge shared] stopAdvertising];
    } else {
        if (requested)
            [[BroadcastBridge shared] stopAdvertising];
        [[BroadcastBridge shared] startBroadcast];
    }
    [self refreshStatus];
}

- (void)testSound:(id)sender {
    (void)sender;
    NSString *error = nil;
    if ([[BroadcastBridge shared] playConnectionTest:&error]) {
        [self refreshStatus];
        NSUInteger active = [self.snapshot[@"active_fingers"]
            unsignedIntegerValue];
        NSString *message = [NSString stringWithFormat:
            @"Listen for the tone on %lu active %@. Hearing it confirms the audio connection.",
            (unsigned long)active,
            active == 1 ? @"finger" : @"fingers"];
        UIAlertController *success = [UIAlertController
            alertControllerWithTitle:@"Test sound sent"
                             message:message
                      preferredStyle:UIAlertControllerStyleAlert];
        [success addAction:[UIAlertAction actionWithTitle:@"Heard it"
                                                   style:UIAlertActionStyleDefault
                                                 handler:nil]];
        __weak BroadcastViewController *weakSelf = self;
        [success addAction:[UIAlertAction actionWithTitle:@"No sound"
                                                   style:UIAlertActionStyleCancel
                                                 handler:^(UIAlertAction *action) {
            (void)action;
            BroadcastViewController *strongSelf = weakSelf;
            if (!strongSelf)
                return;
            strongSelf.modeControl.selectedSegmentIndex = 1;
            [strongSelf changeMode:strongSelf.modeControl];
        }]];
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

- (void)changeMode:(UISegmentedControl *)sender {
    NSString *error = nil;
    BOOL multidevice = sender.selectedSegmentIndex == 0;
    if ([[BroadcastBridge shared]
        setMultideviceMode:multidevice error:&error]) {
        [self refreshStatus];
        return;
    }
    UIAlertController *alert = [UIAlertController
        alertControllerWithTitle:@"Audio mode did not start"
                         message:error ?: @"unknown_audio_error"
                  preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"OK"
                                              style:UIAlertActionStyleDefault
                                            handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (void)refreshStatus {
    NSString *line = [[BroadcastBridge shared] statusLine];
    NSData *data = [line dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *snapshot = data ? [NSJSONSerialization
        JSONObjectWithData:data options:0 error:nil] : nil;
    if (![snapshot isKindOfClass:NSDictionary.class])
        return;
    self.snapshot = snapshot;
    NSArray *devices = snapshot[@"devices"];
    self.devices = [devices isKindOfClass:NSArray.class] ? devices : @[];

    BOOL running = [snapshot[@"running"] boolValue];
    BOOL requested = [snapshot[@"broadcast_requested"] boolValue];
    NSUInteger fingers = [snapshot[@"fingers"] unsignedIntegerValue];
    NSUInteger activeFingers = [snapshot[@"active_fingers"]
        unsignedIntegerValue];
    NSUInteger maximum = [snapshot[@"maximum_fingers"] unsignedIntegerValue];
    NSUInteger mapped = [snapshot[@"mapped_channels"] unsignedIntegerValue];
    NSString *mode = snapshot[@"audio_session_mode"] ?: @"inactive";
    NSString *bluetooth = snapshot[@"bluetooth_state"] ?: @"unknown";
    BOOL advertising = [snapshot[@"advertising"] boolValue];
    BOOL multidevice = [snapshot[@"multidevice_requested"] boolValue];
    self.modeControl.selectedSegmentIndex =
        multidevice ? 0 : 1;
    self.summaryLabel.text = [NSString stringWithFormat:
        @"%@  •  %lu active / %lu bound / %lu max\n%lu mapped channels  •  Audio: %@\nBluetooth: %@%@",
        running ? @"Running" : @"Stopped",
        (unsigned long)activeFingers,
        (unsigned long)fingers,
        (unsigned long)maximum,
        (unsigned long)mapped,
        mode,
        bluetooth,
        advertising ? @"  •  advertising" : @""];
    NSString *startTitle = running ? @"Stop" :
        (requested ? @"Retry" : @"Start");
    [self.startButton setTitle:startTitle
                      forState:UIControlStateNormal];
    self.testButton.enabled = running && mapped > 0;
    id error = snapshot[@"error"];
    if ([error isKindOfClass:NSString.class]) {
        self.errorLabel.text = error;
    } else if (running && activeFingers == 0) {
        self.errorLabel.text = multidevice
            ? @"No active finger yet. Multi uses eligible Bluetooth HFP/LE routes; use Compatible for an ordinary Bluetooth speaker."
            : @"No active finger yet. Tap Choose Audio and select the paired Bluetooth speaker.";
    } else if (multidevice && ![mode isEqualToString:@"dualRoute"]) {
        self.errorLabel.text =
            @"Multi is unavailable on this route, so one compatible output is active.";
    } else {
        self.errorLabel.text = @"";
    }
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
    return @"Audio fingers";
}

- (UITableViewCell *)tableView:(UITableView *)tableView
         cellForRowAtIndexPath:(NSIndexPath *)indexPath
{
    static NSString *identifier = @"BroadcastFingerCell";
    UITableViewCell *cell = [tableView
        dequeueReusableCellWithIdentifier:identifier];
    if (!cell)
        cell = [[UITableViewCell alloc]
            initWithStyle:UITableViewCellStyleSubtitle
            reuseIdentifier:identifier];

    if (self.devices.count == 0) {
        cell.textLabel.text = @"No external audio output active";
        cell.detailTextLabel.text =
            @"Tap Choose Audio, then connect a Bluetooth output.";
        cell.accessoryType = UITableViewCellAccessoryNone;
        cell.selectionStyle = UITableViewCellSelectionStyleNone;
        return cell;
    }

    NSDictionary *device = self.devices[indexPath.row];
    cell.textLabel.text = device[@"name"] ?: @"unknown";
    cell.detailTextLabel.text = [NSString stringWithFormat:@"%@ • %@",
        device[@"finger_state"] ?: @"unknown",
        [device[@"active_route"] boolValue] ? @"active route" : @"waiting"];
    cell.accessoryType = [device[@"finger"] boolValue]
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
    if ([device[@"finger"] boolValue])
        [[BroadcastBridge shared] unbindFinger:identifier error:&error];
    else
        [[BroadcastBridge shared] bindFinger:identifier error:&error];
    [self refreshStatus];
}

@end
