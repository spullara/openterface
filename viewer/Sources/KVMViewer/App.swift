import AppKit
@preconcurrency import AVFoundation
import ViewerCore

@MainActor
final class VideoView: NSView {
    let preview: AVCaptureVideoPreviewLayer
    var mouse: ((NSEvent) -> Void)?
    init(session: AVCaptureSession) {
        preview = AVCaptureVideoPreviewLayer(session: session)
        super.init(frame: .zero)
        wantsLayer = true
        preview.videoGravity = .resizeAspect
        layer?.addSublayer(preview)
    }
    required init?(coder: NSCoder) { fatalError() }
    override var acceptsFirstResponder: Bool { true }
    override func layout() { super.layout(); preview.frame = bounds }
    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        trackingAreas.forEach(removeTrackingArea)
        addTrackingArea(NSTrackingArea(rect: bounds, options: [.activeInKeyWindow, .mouseMoved, .inVisibleRect], owner: self))
    }
    override func mouseMoved(with event: NSEvent) { mouse?(event) }
    override func mouseDown(with event: NSEvent) { mouse?(event) }
    override func mouseUp(with event: NSEvent) { mouse?(event) }
    override func rightMouseDown(with event: NSEvent) { mouse?(event) }
    override func rightMouseUp(with event: NSEvent) { mouse?(event) }
    override func mouseDragged(with event: NSEvent) { mouse?(event) }
    override func rightMouseDragged(with event: NSEvent) { mouse?(event) }
    override func scrollWheel(with event: NSEvent) { mouse?(event) }
}
@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSWindowDelegate {
    let camera = Camera()
    let serial = SerialWriter()
    var bridge: Bridge?
    var agentTyping = false
    var window: NSWindow!
    var video: VideoView!
    var badge = NSTextField(labelWithString: "Control OFF — click the video to take control")
    var statusItem: NSStatusItem!
    var videoStatus = "Video starting"
    var serialStatus = "Serial starting"
    var control = false
    var keys: Set<UInt8> = []
    var buttons: UInt8 = 0
    var monitor: Any?
    var controlButton: NSButton!
    let sleepHint = NSTextField(labelWithString: "Target display may be asleep — click Wake target")
    var releaseTap = DoubleTap()
    var suppressClick = false
    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 960, height: 540), styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "KVM Viewer"
        window.contentAspectRatio = NSSize(width: 16, height: 9)
        window.level = .floating
        window.delegate = self
        window.acceptsMouseMovedEvents = true
        video = VideoView(session: camera.session)
        let content = NSView()
        window.contentView = content
        video.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(video)
        controlButton = NSButton(title: "Take control", target: self, action: #selector(toggleControl))
        let wakeButton = NSButton(title: "Wake target", target: self, action: #selector(wakeTarget))
        let bar = NSStackView(views: [badge, controlButton, wakeButton])
        bar.translatesAutoresizingMaskIntoConstraints = false
        content.addSubview(bar)
        badge.maximumNumberOfLines = 3
        sleepHint.translatesAutoresizingMaskIntoConstraints = false
        sleepHint.drawsBackground = true
        sleepHint.backgroundColor = .windowBackgroundColor
        sleepHint.isHidden = true
        video.addSubview(sleepHint)
        NSLayoutConstraint.activate([
            bar.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 8),
            bar.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -8),
            bar.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -8),
            video.leadingAnchor.constraint(equalTo: content.leadingAnchor),
            video.trailingAnchor.constraint(equalTo: content.trailingAnchor),
            video.topAnchor.constraint(equalTo: content.topAnchor),
            video.bottomAnchor.constraint(equalTo: bar.topAnchor, constant: -8),
            sleepHint.centerXAnchor.constraint(equalTo: video.centerXAnchor),
            sleepHint.centerYAnchor.constraint(equalTo: video.centerYAnchor)
        ])
        window.contentMinSize = NSSize(width: 760, height: 428)
        camera.onBlackHint = { [weak self] show in Task { @MainActor in self?.sleepHint.isHidden = !show } }
        video.mouse = { [weak self] event in self?.mouse(event) }
        let menu = NSMenu()
        for (title, action) in [("Toggle control (Ctrl+Option+Cmd+K)", #selector(toggleControl)), ("Toggle always on top", #selector(toggleFloating)), ("Reconnect serial", #selector(connect)), ("Quit KVM Viewer", #selector(quit))] {
            let item = menu.addItem(withTitle: title, action: action, keyEquivalent: "")
            item.target = self
        }
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.menu = menu
        let main = NSMenu(); let root = main.addItem(withTitle: "KVM Viewer", action: nil, keyEquivalent: ""); root.submenu = menu.copy() as? NSMenu; NSApp.mainMenu = main
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.keyDown, .keyUp, .flagsChanged]) { [weak self] event in
            self?.key(event)
        }
        window.center(); window.makeKeyAndOrderFront(nil); NSApp.activate(ignoringOtherApps: true)
        let bridge = Bridge(serial: serial, frames: camera.frames)
        self.bridge = bridge
        bridge.activity = { [weak self] active in Task { @MainActor in self?.agentTyping = active; self?.refresh() } }
        do { try bridge.start() } catch { serialStatus = "Bridge failed: \(error.localizedDescription)" }
        connect()
        camera.start { [weak self] state in Task { @MainActor in self?.videoStatus = state; self?.refresh() } }
    }
    func refresh() {
        badge.stringValue = (agentTyping ? "Agent typing · " : "") + (control ? "Control ON — Release button or F13 twice" : "Control OFF — click the video to take control") + "\n\(videoStatus) · \(serialStatus)"
        controlButton.title = control ? "Release control" : "Take control"
        statusItem.button?.title = "KVM \(videoStatus == "Video connected" ? "V✓" : "V!") \(serialStatus == "Serial connected" ? "S✓" : "S!")"
    }
    @objc func connect() { release(); serial.connect { [weak self] state in Task { @MainActor in self?.serialStatus = state; self?.refresh() } } }
    @objc func toggleControl() { if control { release() }; control.toggle(); releaseTap.reset(); refresh() }
    @objc func wakeTarget() {
        release()
        send(2, HID.keyboard([], modifiers: 2))
        send(2, HID.keyboard([], modifiers: 0))
        send(5, [1,0,1,0,0])
        send(5, [1,0,255,0,0])
    }
    @objc func toggleFloating() { window.level = window.level == .floating ? .normal : .floating }
    @objc func quit() { release(); serial.send(2, payload: HID.keyboard([], modifiers: 0)) { _ in Task { @MainActor in NSApp.terminate(nil) } } }
    func send(_ command: UInt8, _ payload: [UInt8]) {
        serial.send(command, payload: payload) { [weak self] error in
            if let error { Task { @MainActor in self?.serialStatus = error; self?.control = false; self?.keys.removeAll(); self?.refresh() } }
        }
    }
    func release() { suppressClick = false; releaseTap.reset(); keys.removeAll(); buttons = 0; send(2, HID.keyboard([], modifiers: 0)); send(5, [1,0,0,0,0]) }
    func windowDidResignKey(_ notification: Notification) { if control { release(); control = false; refresh() } }
    func windowShouldClose(_ sender: NSWindow) -> Bool { quit(); return false }
    func key(_ event: NSEvent) -> NSEvent? {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if event.type == .keyDown && event.keyCode == 40 && flags.contains([.control, .option, .command]) { if !event.isARepeat { toggleControl() }; return nil }
        guard control, window.isKeyWindow else { return event }
        if event.keyCode == 105 {
            if event.type == .keyDown && !event.isARepeat && releaseTap.press(at: event.timestamp) { toggleControl() }
            return nil
        }
        if event.type == .keyDown { releaseTap.reset() }
        var modifiers: UInt8 = 0
        for (flag, bit): (NSEvent.ModifierFlags, UInt8) in [(.control,1),(.shift,2),(.option,4),(.command,8)] { if flags.contains(flag) { modifiers |= bit } }
        if let usage = HID.usages[event.keyCode] {
            if event.type == .keyDown { keys.insert(usage) }
            if event.type == .keyUp { keys.remove(usage) }
        }
        send(2, HID.keyboard(keys, modifiers: modifiers))
        return nil
    }
    func mouse(_ event: NSEvent) {
        guard window.isKeyWindow else { return }
        let p = video.convert(event.locationInWindow, from: nil)
        let size = video.bounds.size
        let width = min(size.width, size.height * 16 / 9)
        let height = width * 9 / 16
        let rect = NSRect(x: (size.width-width)/2, y: (size.height-height)/2, width: width, height: height)
        guard rect.width > 0, rect.height > 0 else { return }
        if !control {
            if event.type == .leftMouseDown && rect.contains(p) { suppressClick = true; toggleControl() }
            return
        }
        if suppressClick {
            if event.type == .leftMouseUp { suppressClick = false }
            return
        }
        let pressed: UInt8 = event.type == .leftMouseDown ? 1 : event.type == .rightMouseDown ? 2 : 0
        let released: UInt8 = event.type == .leftMouseUp ? 1 : event.type == .rightMouseUp ? 2 : 0
        if let payload = HID.pointerReport(x: (p.x-rect.minX)/rect.width,
                                           y: 1-(p.y-rect.minY)/rect.height,
                                           buttons: &buttons, pressed: pressed, released: released,
                                           wheel: event.type == .scrollWheel ? Int(event.scrollingDeltaY.rounded()) : 0) {
            send(4, payload)
        }
    }
}
@main struct Main {
    @MainActor static func main() {
        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.setActivationPolicy(.regular)
        app.delegate = delegate
        app.run()
        withExtendedLifetime(delegate) {}
    }
}
