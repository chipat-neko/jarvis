//! build.rs pour jarvis-voice — codegen Rust depuis proto/.
//!
//! Compile au cargo build :
//!   - proto/common.proto  → types partagés (jarvis.common.v1)
//!   - proto/voice.proto   → service + clients pour jarvis.voice.v1

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let proto_root = "../../proto";

    tonic_build::configure()
        .build_server(true)
        .build_client(true)
        .compile_protos(
            &[
                format!("{proto_root}/common.proto"),
                format!("{proto_root}/voice.proto"),
            ],
            &[proto_root],
        )?;

    // Rebuild si les .proto changent
    println!("cargo:rerun-if-changed={proto_root}/common.proto");
    println!("cargo:rerun-if-changed={proto_root}/voice.proto");

    Ok(())
}
