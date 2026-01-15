#![allow(unsafe_op_in_unsafe_fn)]

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use openmls::{prelude::{*, tls_codec::*}};
use openmls_rust_crypto::OpenMlsRustCrypto;
use openmls_basic_credential::SignatureKeyPair;

const CIPHERSUITE: Ciphersuite = Ciphersuite::MLS_128_DHKEMP256_AES128GCM_SHA256_P256;

fn user_id_identity(user_id: &str) -> Vec<u8> {
    let id_int: u64 = user_id.parse().unwrap();
    id_int.to_be_bytes().to_vec()
}

fn build_key_package_bundle(provider: &OpenMlsRustCrypto, user_id: &str) -> KeyPackageBundle {
    let credential = BasicCredential::new(user_id_identity(user_id));
    let signer =
        SignatureKeyPair::new(CIPHERSUITE.signature_algorithm())
            .expect("Error generating a signature key pair.");
    let credential_with_key = CredentialWithKey {
        credential: credential.into(),
        signature_key: signer.public().into(),
    };
    let lifetime = Lifetime::init(0, u64::MAX);
    let capabilities = Capabilities::new(
        Some(&[ProtocolVersion::Mls10]),
        Some(&[CIPHERSUITE]),
        None,
        None,
        Some(&[CredentialType::Basic]));

    signer.store(provider.storage()).expect("Failed to store signature keys");

    KeyPackage::builder()
        .key_package_lifetime(lifetime)
        .key_package_extensions(Extensions::empty())
        .leaf_node_extensions(Extensions::empty())
        .leaf_node_capabilities(capabilities)
        .build(
            CIPHERSUITE,
            provider,
            &signer,
            credential_with_key,
        )
        .expect("Failed to build KeyPackageBundle")
}

#[pyclass]
pub struct DaveSession {
    provider: OpenMlsRustCrypto,
    key_package_bundle: KeyPackageBundle,
    mls_group: Option<MlsGroup>,
}

#[pymethods]
impl DaveSession {
    #[new]
    fn new(user_id: &str) -> Self {
        let provider = OpenMlsRustCrypto::default();
        let kpb = build_key_package_bundle(&provider, user_id);

        Self {
            provider: provider,
            key_package_bundle: kpb,
            mls_group: None
        }
    }

    fn init_mls_group(&mut self, external_sender_identity: &[u8], external_sender_signature: &[u8], welcome: &[u8]) { 
        let _external_sender = ExternalSender::new(SignaturePublicKey::from(external_sender_signature), BasicCredential::new(external_sender_identity.to_vec()).into());
        let welcome = Welcome::tls_deserialize_exact(welcome)
            .expect("Failed to deserialize welcome message");
        let group_config = MlsGroupJoinConfig::builder()
            .use_ratchet_tree_extension(true)
            .build();
        let processed_welcome = ProcessedWelcome::new_from_welcome(
            &self.provider,
            &group_config,
            welcome
        ).expect("Failed to process welcome message");
        let group_info = processed_welcome.unverified_group_info();
        println!("PROCESSED WELCOME GROUP INFO: {:?}", group_info);
    }

    fn get_key_package_message(&self, py: Python<'_>) -> PyObject {
        let bytes_vec = self.key_package_bundle
            .key_package()
            .tls_serialize_detached()
            .expect("Failed to serialize key package");
        PyBytes::new(py, &bytes_vec).into()
    }
}

#[pymodule]
fn openmls_dave(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_class::<DaveSession>()?;
    Ok(())
}
