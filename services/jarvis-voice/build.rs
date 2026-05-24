//! build.rs pour jarvis-voice : codegen Rust depuis proto/voice.proto + common.proto.
//!
//! Decommenter quand on attaque le sprint gRPC (cf card "Setup gRPC proto + codegen").

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // tonic_build::configure()
    //     .build_server(true)
    //     .build_client(true)
    //     .compile(
    //         &["../../proto/voice.proto", "../../proto/common.proto"],
    //         &["../../proto"],
    //     )?;
    Ok(())
}
