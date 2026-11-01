public struct DoubleTap {
    private var previous: Double?
    public init() {}
    public mutating func press(at time: Double) -> Bool {
        if let previous, time >= previous, time - previous <= 0.4 { self.previous = nil; return true }
        previous = time
        return false
    }
    public mutating func reset() { previous = nil }
}
public struct BlackFrameHint {
    private var since: Double?
    public init() {}
    public mutating func update(samples: [UInt8], at time: Double) -> Bool {
        let black = !samples.isEmpty && Double(samples.filter { $0 <= 24 }.count) / Double(samples.count) >= 0.99
        guard black else { since = nil; return false }
        if since == nil { since = time }
        return time - (since ?? time) >= 2
    }
}
