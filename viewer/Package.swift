// swift-tools-version: 6.0
import PackageDescription
let package = Package(name: "KVMViewer", platforms: [.macOS(.v14)], products: [.executable(name: "KVMViewer", targets: ["KVMViewer"])], targets: [.target(name: "ViewerCore"), .executableTarget(name: "KVMViewer", dependencies: ["ViewerCore"]), .testTarget(name: "ViewerCoreTests", dependencies: ["ViewerCore"])])
