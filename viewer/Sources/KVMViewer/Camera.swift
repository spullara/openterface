@preconcurrency import AVFoundation
import AppKit
import ViewerCore

// The buffer owns only the newest immutable frame. Bridge readers can take a snapshot.
final class LatestFrameBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private var frame: CVPixelBuffer?
    func store(_ value: CVPixelBuffer) { lock.lock(); frame = value; lock.unlock() }
    func read() -> CVPixelBuffer? { lock.lock(); defer { lock.unlock() }; return frame }
}
final class Camera: NSObject, AVCaptureVideoDataOutputSampleBufferDelegate, @unchecked Sendable {
    let session = AVCaptureSession()
    let frames = LatestFrameBuffer()
    private let queue = DispatchQueue(label: "kvm.camera")
    func start(status: @escaping @Sendable (String) -> Void) {
        AVCaptureDevice.requestAccess(for: .video) { [self] allowed in
            guard allowed else { status("Camera denied. Enable KVM Viewer in System Settings > Privacy & Security > Camera."); return }
            queue.async { [self] in
                let devices = AVCaptureDevice.DiscoverySession(deviceTypes: [.external], mediaType: .video, position: .unspecified).devices
                guard let device = devices.first(where: { $0.localizedName.contains("Openterface") }) else { status("Openterface camera is missing. Reconnect and restart the viewer."); return }
                do {
                    let input = try AVCaptureDeviceInput(device: device)
                    session.beginConfiguration()
                    guard session.canAddInput(input) else { session.commitConfiguration(); status("Cannot open camera."); return }
                    session.addInput(input)
                    let output = AVCaptureVideoDataOutput()
                    output.alwaysDiscardsLateVideoFrames = true
                    output.setSampleBufferDelegate(self, queue: queue)
                    guard session.canAddOutput(output) else { session.commitConfiguration(); status("Cannot read camera frames."); return }
                    session.addOutput(output)
                    let formats = device.formats
                    let values = formats.map { format in
                        let dimensions = CMVideoFormatDescriptionGetDimensions(format.formatDescription)
                        return VideoFormat(width: dimensions.width, height: dimensions.height,
                                           subtype: CMFormatDescriptionGetMediaSubType(format.formatDescription),
                                           ranges: format.videoSupportedFrameRateRanges.map {
                                               .init(min: $0.minFrameRate, max: $0.maxFrameRate)
                                           })
                    }
                    guard let selection = VideoFormat.select(values) else { session.commitConfiguration(); status("Camera has no supported 1080p or 720p mode at 30 fps."); return }
                    let format = formats[selection.format]
                    let range = format.videoSupportedFrameRateRanges[selection.range]
                    try device.lockForConfiguration()
                    device.activeFormat = format
                    device.activeVideoMinFrameDuration = range.minFrameDuration
                    device.activeVideoMaxFrameDuration = range.maxFrameDuration
                    device.unlockForConfiguration()
                    session.commitConfiguration()
                    session.startRunning()
                    status("Video connected")
                } catch { status("Camera error: \(error.localizedDescription)") }
            }
        }
    }
    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        if let buffer = CMSampleBufferGetImageBuffer(sampleBuffer) { frames.store(buffer) }
    }
}
