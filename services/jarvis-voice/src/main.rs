//! jarvis-voice — service Rust pour le pipeline voice temps réel.
//!
//! Skeleton initial avec gRPC server `VoiceService` qui expose Ping/Pong.
//! Les vrais RPC (StreamAudio, Transcribe, Synthesize, DetectWakeWord) seront
//! implémentés en S3-S4 (cf TODO proto/voice.proto).
//!
//! Cf docs/adr/0001-microservices-python-rust.md.

use std::net::SocketAddr;

use anyhow::Result;
use tonic::{transport::Server, Request, Response, Status as TonicStatus};
use tracing::info;
use tracing_subscriber::EnvFilter;

// Code généré par tonic-build depuis proto/voice.proto et proto/common.proto.
pub mod jarvis {
    pub mod common {
        pub mod v1 {
            tonic::include_proto!("jarvis.common.v1");
        }
    }
    pub mod voice {
        pub mod v1 {
            tonic::include_proto!("jarvis.voice.v1");
        }
    }
}

use jarvis::common::v1::status::Code as StatusCode;
use jarvis::common::v1::Status as JarvisStatus;
use jarvis::voice::v1::voice_service_server::{VoiceService, VoiceServiceServer};
use jarvis::voice::v1::{PingRequest, PingResponse};

/// Implémentation par défaut du service voice.
///
/// Pour l'instant n'expose que Ping. Les vrais RPC arrivent en S3-S4.
#[derive(Debug, Default)]
pub struct VoiceServiceImpl;

#[tonic::async_trait]
impl VoiceService for VoiceServiceImpl {
    async fn ping(
        &self,
        request: Request<PingRequest>,
    ) -> Result<Response<PingResponse>, TonicStatus> {
        let req = request.into_inner();
        info!(client_id = %req.client_id, "Ping reçu");

        let resp = PingResponse {
            status: Some(JarvisStatus {
                code: StatusCode::Ok as i32,
                message: format!("Pong from jarvis-voice (client_id={})", req.client_id),
            }),
            version: env!("CARGO_PKG_VERSION").to_string(),
        };

        Ok(Response::new(resp))
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")))
        .init();

    let addr: SocketAddr = "127.0.0.1:50051".parse()?;
    let service = VoiceServiceImpl;

    info!(
        version = env!("CARGO_PKG_VERSION"),
        listen = %addr,
        "jarvis-voice gRPC server starting"
    );
    info!("RPC exposés : Ping (TODO S3-S4 : StreamAudio, Transcribe, Synthesize, DetectWakeWord)");

    Server::builder()
        .add_service(VoiceServiceServer::new(service))
        .serve(addr)
        .await?;

    Ok(())
}
