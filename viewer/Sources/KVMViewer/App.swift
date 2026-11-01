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
    var window: NSWindow!
    var video: VideoView!
    var badge = NSTextField(labelWithString: "Control OFF — Ctrl+Option+Cmd+K")
    var statusItem: NSStatusItem!
    var videoStatus = "Video starting"
    var serialStatus = "Serial starting"
    var control = false
    var keys: Set<UInt8> = []
    var buttons: UInt8 = 0
    var monitor: Any?
    func applicationDidFinishLaunching(_ notification: Notification) {
        window = NSWindow(contentRect: NSRect(x: 100, y: 100, width: 960, height: 540), styleMask: [.titled, .closable, .resizable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "KVM Viewer"
        window.contentAspectRatio = NSSize(width: 16, height: 9)
        window.level = .floating
        window.delegate = self
        window.acceptsMouseMovedEvents = true
        video = VideoView(session: camera.session)
        window.contentView = video
        badge.translatesAutoresizingMaskIntoConstraints = false
        badge.backgroundColor = .windowBackgroundColor
        badge.drawsBackground = true
        video.addSubview(badge)
        NSLayoutConstraint.activate([badge.leadingAnchor.constraint(equalTo: video.leadingAnchor, constant: 8), badge.topAnchor.constraint(equalTo: video.topAnchor, constant: 8), badge.trailingAnchor.constraint(lessThanOrEqualTo: video.trailingAnchor, constant: -8)])
        badge.maximumNumberOfLines = 3
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
        connect()
        camera.start { [weak self] state in Task { @MainActor in self?.videoStatus = state; self?.refresh() } }
    }
    func refresh() {
        badge.stringValue = "Control \(control ? "ON" : "OFF") — Ctrl+Option+Cmd+K\n\(videoStatus) · \(serialStatus)"
        statusItem.button?.title = "KVM \(videoStatus == "Video connected" ? "V✓" : "V!") \(serialStatus == "Serial connected" ? "S✓" : "S!")"
    }
    @objc func connect() { release(); serial.connect { [weak self] state in Task { @MainActor in self?.serialStatus = state; self?.refresh() } } }
    @objc func toggleControl() { if control { release() }; control.toggle(); refresh() }
    @objc func toggleFloating() { window.level = window.level == .floating ? .normal : .floating }
    @objc func quit() { release(); serial.send(2, payload: HID.keyboard([], modifiers: 0)) { _ in Task { @MainActor in NSApp.terminate(nil) } } }
    func send(_ command: UInt8, _ payload: [UInt8]) {
        serial.send(command, payload: payload) { [weak self] error in
            if let error { Task { @MainActor in self?.serialStatus = error; self?.control = false; self?.keys.removeAll(); self?.refresh() } }
        }
    }
    func release() { keys.removeAll(); buttons = 0; send(2, HID.keyboard([], modifiers: 0)); send(5, [1,0,0,0,0]) }
    func windowDidResignKey(_ notification: Notification) { if control { release(); control = false; refresh() } }
    func windowShouldClose(_ sender: NSWindow) -> Bool { quit(); return false }
    func key(_ event: NSEvent) -> NSEvent? {
        let flags = event.modifierFlags.intersection(.deviceIndependentFlagsMask)
        if event.type == .keyDown && event.keyCode == 40 && flags.contains([.control, .option, .command]) { if !event.isARepeat { toggleControl() }; return nil }
        guard control, window.isKeyWindow else { return event }
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
        guard control, window.isKeyWindow else { return }
        let p = video.convert(event.locationInWindow, from: nil)
        let size = video.bounds.size
        let width = min(size.width, size.height * 16 / 9)
        let height = width * 9 / 16
        let rect = NSRect(x: (size.width-width)/2, y: (size.height-height)/2, width: width, height: height)
        guard rect.contains(p), rect.width > 0 else { return }
        if event.type == .leftMouseDown { buttons |= 1 }
        if event.type == .leftMouseUp { buttons &= ~1 }
        if event.type == .rightMouseDown { buttons |= 2 }
        if event.type == .rightMouseUp { buttons &= ~2 }
        send(4, HID.mouse(x: (p.x-rect.minX)/rect.width, y: 1-(p.y-rect.minY)/rect.height, buttons: buttons, wheel: event.type == .scrollWheel ? Int(event.scrollingDeltaY.rounded()) : 0))
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
