@preconcurrency import AVFoundation
import AppKit

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
                    let format = [1920, 1280].compactMap { width in
                        device.formats.first { f in
                            let d = CMVideoFormatDescriptionGetDimensions(f.formatDescription)
                            return d.width == width && d.height == (width == 1920 ? 1080 : 720) && f.videoSupportedFrameRateRanges.contains { $0.minFrameRate <= 30 && $0.maxFrameRate >= 30 }
                        }
                    }.first
                    guard let format else { session.commitConfiguration(); status("Camera has no supported 1080p or 720p mode at 30 fps."); return }
                    try device.lockForConfiguration()
                    device.activeFormat = format
                    device.activeVideoMinFrameDuration = CMTime(value: 1, timescale: 30)
                    device.activeVideoMaxFrameDuration = CMTime(value: 1, timescale: 30)
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
