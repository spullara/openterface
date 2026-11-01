import Foundation
import Darwin
import IOKit
import IOKit.serial

// All port operations and complete request/ACK transactions use this single queue.
public final class SerialWriter: @unchecked Sendable {
    private let queue = DispatchQueue(label: "kvm.serial")
    private var fd: Int32 = -1
    public init() {}
    public static func ports() -> [String] {
        var iterator: io_iterator_t = 0
        guard IOServiceGetMatchingServices(kIOMainPortDefault, IOServiceMatching(kIOSerialBSDServiceValue), &iterator) == KERN_SUCCESS else { return [] }
        defer { IOObjectRelease(iterator) }
        var paths: [String] = []
        while case let service = IOIteratorNext(iterator), service != 0 {
            defer { IOObjectRelease(service) }
            func property(_ key: String) -> Any? {
                IORegistryEntrySearchCFProperty(service, kIOServicePlane, key as CFString, kCFAllocatorDefault, IOOptionBits(kIORegistryIterateRecursively | kIORegistryIterateParents))
            }
            if (property("idVendor") as? NSNumber)?.intValue == 0x1a86,
               (property("idProduct") as? NSNumber)?.intValue == 0xfe0c,
               let path = property(kIOCalloutDeviceKey) as? String { paths.append(path) }
        }
        return paths
    }
    public func connect(completion: @escaping @Sendable (String) -> Void) {
        queue.async { [self] in
            if fd >= 0 { Darwin.close(fd); fd = -1 }
            let ports = Self.ports()
            guard ports.count == 1 else { completion("Connect one Openterface serial device."); return }
            fd = Darwin.open(ports[0], O_RDWR | O_NOCTTY | O_NONBLOCK)
            guard fd >= 0 else { completion("Cannot open serial device."); return }
            var options = termios()
            guard tcgetattr(fd, &options) == 0 else { fail(completion); return }
            cfmakeraw(&options)
            cfsetspeed(&options, speed_t(B115200))
            options.c_cflag |= tcflag_t(CLOCAL | CREAD)
            guard tcsetattr(fd, TCSANOW, &options) == 0 else { fail(completion); return }
            completion("Serial connected")
        }
    }
    private func fail(_ completion: @Sendable (String) -> Void) {
        if fd >= 0 { Darwin.close(fd); fd = -1 }
        completion("Serial error. Reconnect the device.")
    }
    public func send(_ command: UInt8, payload: [UInt8], completion: @escaping @Sendable (String?) -> Void = { _ in }) {
        queue.async { [self] in
            guard fd >= 0 else { completion("Serial is not connected."); return }
            tcflush(fd, TCIFLUSH)
            let packet = HID.packet(command, payload)
            let written = packet.withUnsafeBytes { Darwin.write(fd, $0.baseAddress, $0.count) }
            var response: [UInt8] = []
            let deadline = Date().addingTimeInterval(0.3)
            while written == packet.count && Date() < deadline {
                var pollFD = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
                if poll(&pollFD, 1, 20) > 0 {
                    var bytes = [UInt8](repeating: 0, count: 64)
                    let n = Darwin.read(fd, &bytes, bytes.count)
                    if n > 0 { response += bytes.prefix(n) }
                    if response.count >= 6, response.count >= Int(response[4])+6 { break }
                }
            }
            if response != HID.packet(command | 0x80, [0]) {
                fail { completion($0) }
            } else { completion(nil) }
        }
    }
}
