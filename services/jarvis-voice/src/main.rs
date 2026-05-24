//! jarvis-voice — service Rust pour le pipeline voice temps reel.
//!
//! Skeleton initial. Sera rempli en S3-S4 (wake word, STT, VAD, TTS).
//! Cf docs/adr/0001-microservices-python-rust.md et proto/voice.proto.

use anyhow::Result;
use tracing::info;
use tracing_subscriber::EnvFilter;

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .init();

    info!("jarvis-voice skeleton starting");
    info!("TODO S3-S4 : implementer wake word + STT + VAD + TTS + gRPC server");
    info!("jarvis-voice up (no-op)");

    // TODO : tonic gRPC server sur localhost:50051
    // let addr = "127.0.0.1:50051".parse()?;
    // Server::builder()
    //     .add_service(VoiceServiceServer::new(VoiceImpl::default()))
    //     .serve(addr).await?;

    Ok(())
}
