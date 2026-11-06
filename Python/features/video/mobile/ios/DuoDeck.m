// Included by VideoPlayer.m. UIKit controls and settings scoped to the lower
// reserved region; the ordinary player keeps its existing native menus.
#import <objc/runtime.h>

static char LGVideoActionHandlerKey, LGVideoDialogHandlersKey;
@interface UIAlertAction (LGVideoDeck)
+ (instancetype)lg_videoActionWithTitle:(NSString *)title style:(UIAlertActionStyle)style handler:(void (^)(UIAlertAction *))handler;
@end
@implementation UIAlertAction (LGVideoDeck)
+ (instancetype)lg_videoActionWithTitle:(NSString *)title style:(UIAlertActionStyle)style handler:(void (^)(UIAlertAction *))handler {
    UIAlertAction *action = [self actionWithTitle:title style:style handler:handler];
    objc_setAssociatedObject(action, &LGVideoActionHandlerKey, handler, OBJC_ASSOCIATION_COPY_NONATOMIC);
    return action;
}
@end

// UIAlertController may copy its actions. Retain callbacks by row on the model
// before UIKit copies them, rather than depending on an action object's identity.
@interface UIAlertController (LGVideoDeck)
- (void)lg_videoAddAction:(UIAlertAction *)action;
@end
@implementation UIAlertController (LGVideoDeck)
- (void)lg_videoAddAction:(UIAlertAction *)action {
    NSMutableArray *handlers = objc_getAssociatedObject(self, &LGVideoDialogHandlersKey);
    if (!handlers) {
        handlers = [NSMutableArray array];
        objc_setAssociatedObject(self, &LGVideoDialogHandlersKey, handlers, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    }
    [handlers addObject:objc_getAssociatedObject(action, &LGVideoActionHandlerKey) ?: NSNull.null];
    [self addAction:action];
}
@end

@interface LGVideoDeckSettings : UITableViewController <UIViewControllerTransitioningDelegate>
@property(nonatomic, weak) LGVideoController *owner;
@property(nonatomic, strong) UIAlertController *dialog;
@end
@interface LGVideoDeckPresentation : UIPresentationController
@property(nonatomic, strong) UIView *backdrop;
@property(nonatomic) CGRect keyboard;
@end
@implementation LGVideoDeckPresentation
- (BOOL)shouldPresentInFullscreen { return NO; }
- (BOOL)shouldRemovePresentersView { return NO; }
- (CGRect)frameOfPresentedViewInContainerView {
    LGVideoDeckSettings *settings = (LGVideoDeckSettings *)self.presentedViewController;
    // Leave a reachable dismissal gutter on every lower-panel edge, including
    // for long chapter/track lists. The upper video panel stays untouched.
    CGRect area = CGRectInset([settings.owner.view convertRect:settings.owner.tabletopArea toView:self.containerView], 24, 24);
    if (!CGRectIsEmpty(self.keyboard)) {
        CGRect keyboard = [self.containerView convertRect:self.keyboard fromView:nil];
        if (CGRectIntersectsRect(area, keyboard)) area.size.height = MAX(44, CGRectGetMinY(keyboard) - area.origin.y);
    }
    CGFloat height = MIN(MAX(44, area.size.height), settings.preferredContentSize.height);
    CGFloat width = MIN(360, MAX(0, area.size.width));
    return CGRectMake(CGRectGetMidX(area) - width / 2, CGRectGetMaxY(area) - height, width, height);
}
- (void)presentationTransitionWillBegin {
    self.backdrop = [[UIView alloc] init];
    self.backdrop.backgroundColor = [UIColor colorWithWhite:0 alpha:.22];
    [self.containerView insertSubview:self.backdrop atIndex:0];
    UITapGestureRecognizer *tap = [[UITapGestureRecognizer alloc] initWithTarget:self action:@selector(dismiss:)];
    [self.backdrop addGestureRecognizer:tap];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(keyboardChanged:) name:UIKeyboardWillChangeFrameNotification object:nil];
}
- (void)containerViewWillLayoutSubviews {
    [super containerViewWillLayoutSubviews];
    LGVideoDeckSettings *settings = (LGVideoDeckSettings *)self.presentedViewController;
    self.backdrop.frame = [settings.owner.view convertRect:settings.owner.tabletopArea toView:self.containerView];
    self.presentedView.frame = self.frameOfPresentedViewInContainerView;
    self.presentedView.layer.cornerRadius = 24;
    self.presentedView.clipsToBounds = YES;
}
- (void)keyboardChanged:(NSNotification *)note {
    self.keyboard = [note.userInfo[UIKeyboardFrameEndUserInfoKey] CGRectValue];
    [self.containerView setNeedsLayout];
}
- (void)dismiss:(id)sender {
    LGVideoDeckSettings *settings = (LGVideoDeckSettings *)self.presentedViewController;
    // Preserve explicit Apply/Cancel for drafts, as in ordinary text prompts.
    if (!settings.dialog.textFields.count) [settings dismissViewControllerAnimated:YES completion:nil];
}
- (void)dismissalTransitionDidEnd:(BOOL)completed {
    if (completed) { [self.backdrop removeFromSuperview]; [NSNotificationCenter.defaultCenter removeObserver:self]; }
}
- (void)dealloc { [NSNotificationCenter.defaultCenter removeObserver:self]; }
@end

@implementation LGVideoDeckSettings
- (void)viewDidLoad {
    [super viewDidLoad];
    self.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
    self.tableView.backgroundColor = UIColor.secondarySystemBackgroundColor;
    self.tableView.rowHeight = UITableViewAutomaticDimension;
    self.tableView.estimatedRowHeight = 48;
    self.tableView.keyboardDismissMode = UIScrollViewKeyboardDismissModeInteractive;
    self.tableView.accessibilityIdentifier = @"video.deck.settings";
    UIStackView *header = [[UIStackView alloc] init];
    header.axis = UILayoutConstraintAxisVertical;
    header.spacing = 10;
    header.layoutMarginsRelativeArrangement = YES;
    header.layoutMargins = UIEdgeInsetsMake(16, 20, 12, 20);
    UIStackView *heading = [[UIStackView alloc] init];
    heading.axis = UILayoutConstraintAxisHorizontal;
    heading.alignment = UIStackViewAlignmentCenter;
    heading.spacing = 12;
    [header addArrangedSubview:heading];
    for (NSString *text in @[self.dialog.title ?: @"", self.dialog.message ?: @""]) {
        if (!text.length) continue;
        UILabel *label = [[UILabel alloc] init]; label.text = text; label.numberOfLines = 0;
        label.font = [UIFont preferredFontForTextStyle:[text isEqualToString:self.dialog.title] ? UIFontTextStyleHeadline : UIFontTextStyleSubheadline];
        label.adjustsFontForContentSizeCategory = YES;
        label.textColor = UIColor.labelColor;
        if ([text isEqualToString:self.dialog.title]) [heading addArrangedSubview:label];
        else [header addArrangedSubview:label];
    }
    if (!self.dialog.textFields.count) {
        UIButton *close = [UIButton buttonWithType:UIButtonTypeSystem];
        [close setImage:[UIImage systemImageNamed:@"xmark"] forState:UIControlStateNormal];
        close.accessibilityLabel = @"Close menu";
        close.accessibilityIdentifier = @"video.deck.settings.close";
        [close.widthAnchor constraintEqualToConstant:44].active = YES;
        [close.heightAnchor constraintEqualToConstant:44].active = YES;
        [close addTarget:self action:@selector(closeMenu:) forControlEvents:UIControlEventTouchUpInside];
        [heading addArrangedSubview:close];
    }
    for (UITextField *field in self.dialog.textFields) {
        [field removeFromSuperview];
        field.borderStyle = UITextBorderStyleRoundedRect;
        [field.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
        [header addArrangedSubview:field];
    }
    self.tableView.tableHeaderView = header;
}
- (void)closeMenu:(id)sender {
    [self dismissViewControllerAnimated:YES completion:nil];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    UIView *header = self.tableView.tableHeaderView;
    CGFloat width = self.tableView.bounds.size.width;
    CGSize size = [header systemLayoutSizeFittingSize:CGSizeMake(width, UILayoutFittingCompressedSize.height)
        withHorizontalFittingPriority:UILayoutPriorityRequired verticalFittingPriority:UILayoutPriorityFittingSizeLevel];
    if (fabs(header.frame.size.height - size.height) > .5 || fabs(header.frame.size.width - width) > .5) {
        header.frame = CGRectMake(0, 0, width, size.height);
        self.tableView.tableHeaderView = header;
    }
}
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return self.dialog.actions.count; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:nil];
    UIAlertAction *action = self.dialog.actions[indexPath.row];
    cell.textLabel.text = action.title;
    cell.textLabel.numberOfLines = 0;
    cell.textLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    cell.textLabel.adjustsFontForContentSizeCategory = YES;
    cell.textLabel.textColor = !action.enabled ? UIColor.tertiaryLabelColor : action.style == UIAlertActionStyleDestructive ? UIColor.systemRedColor : UIColor.labelColor;
    cell.backgroundColor = UIColor.secondarySystemBackgroundColor;
    [cell.heightAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
    cell.accessibilityTraits |= UIAccessibilityTraitButton;
    return cell;
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    UIAlertAction *action = self.dialog.actions[indexPath.row];
    if (!action.enabled || self.owner.retired || self.owner.lockHidden) return;
    NSArray *handlers = objc_getAssociatedObject(self.dialog, &LGVideoDialogHandlersKey);
    id callback = handlers[indexPath.row];
    void (^handler)(UIAlertAction *) = callback == NSNull.null ? nil : callback;
    [self.view endEditing:YES];
    [self dismissViewControllerAnimated:YES completion:^{
        if (handler && !self.owner.retired && !self.owner.lockHidden) handler(action);
    }];
}
- (UIPresentationController *)presentationControllerForPresentedViewController:(UIViewController *)presented presentingViewController:(UIViewController *)presenting sourceViewController:(UIViewController *)source {
    return [[LGVideoDeckPresentation alloc] initWithPresentedViewController:presented presentingViewController:presenting];
}
@end

@implementation LGVideoController (PortraitDeck)
- (void)presentPortraitMenu:(UIAlertController *)dialog {
    if (self.presentedViewController) {
        [self.presentedViewController dismissViewControllerAnimated:NO completion:^{ [self presentPlaybackDialog:dialog]; }];
        return;
    }
    LGVideoDeckSettings *settings = [[LGVideoDeckSettings alloc] initWithStyle:UITableViewStylePlain];
    settings.owner = self;
    settings.dialog = dialog;
    settings.preferredContentSize = CGSizeMake(400, 84 + dialog.actions.count * 52 + dialog.textFields.count * 54 + (dialog.message.length ? 44 : 0));
    settings.modalPresentationStyle = UIModalPresentationCustom;
    settings.transitioningDelegate = settings;
    [self presentViewController:settings animated:YES completion:nil];
}
- (void)installPortraitDeck {
    self.portraitHeader = [[UIStackView alloc] init];
    self.portraitHeader.alignment = UIStackViewAlignmentCenter;
    self.portraitHeader.spacing = 12;
    self.portraitClose = [UIButton buttonWithType:UIButtonTypeSystem];
    UIButtonConfiguration *close = [UIButtonConfiguration tintedButtonConfiguration];
    close.image = [UIImage systemImageNamed:@"xmark"];
    close.baseForegroundColor = UIColor.whiteColor;
    close.baseBackgroundColor = UIColor.secondarySystemBackgroundColor;
    close.cornerStyle = UIButtonConfigurationCornerStyleCapsule;
    self.portraitClose.configuration = close;
    self.portraitClose.accessibilityLabel = @"Close video";
    self.portraitClose.accessibilityIdentifier = @"video.deck.close";
    [self.portraitClose.widthAnchor constraintEqualToConstant:44].active = YES;
    [self.portraitClose.heightAnchor constraintEqualToConstant:44].active = YES;
    [self.portraitClose addTarget:self action:@selector(done:) forControlEvents:UIControlEventTouchUpInside];
    [self.portraitHeader addArrangedSubview:self.portraitClose];
    [self.controls insertArrangedSubview:self.portraitHeader atIndex:0];
    self.portraitHeader.hidden = YES;
    UIVisualEffect *effect;
    if (@available(iOS 26.0, *)) effect = [UIGlassEffect effectWithStyle:UIGlassEffectStyleRegular];
    else effect = [UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemThinMaterialDark];
    self.portraitToolbar = [[UIVisualEffectView alloc] initWithEffect:effect];
    self.portraitToolbar.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
    self.portraitToolbar.layer.cornerRadius = 24;
    self.portraitToolbar.clipsToBounds = YES;
    self.portraitUtilities = [[UIStackView alloc] init];
    self.portraitUtilities.distribution = UIStackViewDistributionFillEqually;
    self.portraitUtilities.translatesAutoresizingMaskIntoConstraints = NO;
    [self.portraitToolbar.contentView addSubview:self.portraitUtilities];
    [NSLayoutConstraint activateConstraints:@[
        [self.portraitUtilities.leadingAnchor constraintEqualToAnchor:self.portraitToolbar.contentView.leadingAnchor constant:4],
        [self.portraitUtilities.trailingAnchor constraintEqualToAnchor:self.portraitToolbar.contentView.trailingAnchor constant:-4],
        [self.portraitUtilities.topAnchor constraintEqualToAnchor:self.portraitToolbar.contentView.topAnchor constant:6],
        [self.portraitUtilities.bottomAnchor constraintEqualToAnchor:self.portraitToolbar.contentView.bottomAnchor constant:-6]]];
    for (NSArray *entry in @[@[@"1×", @"speedometer", @"speedOptions:", @"Speed"],
                            @[@"Fill", @"arrow.up.left.and.arrow.down.right", @"togglePictureSize:", @"Fill view"],
                            @[@"Audio", @"speaker.wave.2", @"audioTracks:", @"Audio"],
                            @[@"Subtitles", @"captions.bubble", @"subtitleTracks:", @"Subtitles"],
                            @[@"Chapters", @"list.bullet", @"chapters:", @"Chapters"],
                            @[@"Playback", @"ellipsis", @"playbackTools:", @"Playback"]]) {
        UIButton *button = [UIButton buttonWithType:UIButtonTypeSystem];
        UIButtonConfiguration *config = [UIButtonConfiguration plainButtonConfiguration];
        config.title = entry[0]; config.image = [UIImage systemImageNamed:entry[1]];
        config.imagePlacement = NSDirectionalRectEdgeTop;
        config.imagePadding = 6;
        config.contentInsets = NSDirectionalEdgeInsetsMake(6, 2, 6, 2);
        config.baseForegroundColor = UIColor.whiteColor;
        config.titleTextAttributesTransformer = ^NSDictionary *(NSDictionary *attributes) {
            NSMutableDictionary *result = attributes.mutableCopy;
            result[NSFontAttributeName] = [UIFont preferredFontForTextStyle:UIFontTextStyleCaption2]; return result;
        };
        button.configuration = config;
        button.accessibilityLabel = entry[3];
        button.accessibilityIdentifier = [@"video.deck." stringByAppendingString:entry[3]];
        [button.heightAnchor constraintGreaterThanOrEqualToConstant:52].active = YES;
        [button.widthAnchor constraintGreaterThanOrEqualToConstant:44].active = YES;
        [button addTarget:self action:NSSelectorFromString(entry[2]) forControlEvents:UIControlEventTouchUpInside];
        [self.portraitUtilities addArrangedSubview:button];
        if ([entry[2] isEqualToString:@"togglePictureSize:"]) self.portraitPictureButton = button;
        if ([entry[2] isEqualToString:@"speedOptions:"]) self.portraitSpeedButton = button;
    }
    [self.controls addArrangedSubview:self.portraitToolbar]; self.portraitToolbar.hidden = YES;
    self.portraitDeckHeight = [self.controlsScroll.heightAnchor constraintEqualToConstant:300];
    self.portraitDeckHeight.priority = 999;
    // Swap fixed button sizes with the pose rather than rebuilding targets.
    NSMutableArray *sizes = [NSMutableArray array];
    for (UIButton *button in self.transport.arrangedSubviews)
        for (NSLayoutConstraint *constraint in button.constraints)
            if ((constraint.firstAttribute == NSLayoutAttributeWidth || constraint.firstAttribute == NSLayoutAttributeHeight) && !constraint.secondItem)
                [sizes addObject:constraint];
    self.transportSizes = sizes;
}
- (void)layoutPortraitDeck {
    BOOL portrait = self.portraitTabletop;
    self.deckHeaderHeight.constant = portrait ? MAX(44, ceil(self.videoTitle.font.lineHeight + self.sourceLabel.font.lineHeight + 2)) : 44;
    self.portraitHeader.hidden = !portrait;
    self.portraitToolbar.hidden = !portrait;
    if (portrait) {
        if (self.videoHeader.superview != self.portraitHeader) {
            self.navigationItem.titleView = nil;
            [self.controls removeArrangedSubview:self.videoHeader]; [self.videoHeader removeFromSuperview];
            self.videoHeader.translatesAutoresizingMaskIntoConstraints = NO;
            self.deckHeaderHeight.active = YES;
            [self.portraitHeader insertArrangedSubview:self.videoHeader atIndex:0];
            for (UIView *view in @[self.seek, self.timeLabel, self.transport]) {
                [self.controls removeArrangedSubview:view]; [view removeFromSuperview];
            }
            [self.controls insertArrangedSubview:self.seek atIndex:1];
            [self.controls insertArrangedSubview:self.timeLabel atIndex:2];
            [self.controls insertArrangedSubview:self.transport atIndex:3];
        }
    } else if (self.videoHeader.superview == self.portraitHeader) {
        [self.portraitHeader removeArrangedSubview:self.videoHeader]; [self.videoHeader removeFromSuperview];
        [self.controls insertArrangedSubview:self.videoHeader atIndex:0];
        for (UIView *view in @[self.timeLabel, self.seek, self.transport]) {
            [self.controls removeArrangedSubview:view]; [view removeFromSuperview];
        }
        [self.controls insertArrangedSubview:self.timeLabel atIndex:3];
        [self.controls insertArrangedSubview:self.seek atIndex:4];
        [self.controls insertArrangedSubview:self.transport atIndex:5];
    }
    if (self.videoTitle.textAlignment != (portrait ? NSTextAlignmentLeft : NSTextAlignmentCenter))
        ((UIVisualEffectView *)self.videoHeader).effect = portrait ? nil : ({
        UIVisualEffect *effect;
        if (@available(iOS 26.0, *)) effect = [UIGlassEffect effectWithStyle:UIGlassEffectStyleRegular];
        else effect = [UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemThinMaterialDark]; effect;
    });
    self.videoTitle.textAlignment = portrait ? NSTextAlignmentLeft : NSTextAlignmentCenter;
    self.videoIdentity.alignment = portrait ? UIStackViewAlignmentLeading : UIStackViewAlignmentCenter;
    self.transport.distribution = UIStackViewDistributionEqualCentering;
    [self.transport setContentHuggingPriority:portrait ? 1 : UILayoutPriorityDefaultLow forAxis:UILayoutConstraintAxisVertical];
    for (NSLayoutConstraint *size in self.transportSizes) {
        BOOL primary = size.firstItem == self.playButton;
        CGFloat primarySize = MIN(80, MAX(64, self.tabletopArea.size.height - 250));
        size.constant = portrait ? (primary ? primarySize : 52) : (primary ? 56 : 48);
    }
    if (!portrait && [self.presentedViewController isKindOfClass:LGVideoDeckSettings.class])
        [self.presentedViewController dismissViewControllerAnimated:NO completion:nil];
    else [self.presentedViewController.presentationController.containerView setNeedsLayout];
}
@end
