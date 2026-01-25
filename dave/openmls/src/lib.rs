#![allow(unsafe_op_in_unsafe_fn)]
#![allow(non_local_definitions)]

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use openmls::{prelude::{*, tls_codec::*}};
use openmls_rust_crypto::OpenMlsRustCrypto;
use openmls_basic_credential::SignatureKeyPair;
use openmls_traits::signatures::Signer;

const CIPHERSUITE: Ciphersuite = Ciphersuite::MLS_128_DHKEMP256_AES128GCM_SHA256_P256;

fn get_dave_capabilities() -> Capabilities {
    Capabilities::new(
        Some(&[ProtocolVersion::Mls10]),
        Some(&[CIPHERSUITE]),
        None,
        None,
        Some(&[CredentialType::Basic]))
}

fn build_key_package_bundle(provider: &OpenMlsRustCrypto, signer: &impl Signer, credential_with_key: CredentialWithKey) -> KeyPackageBundle {
    KeyPackage::builder()
        .key_package_lifetime(Lifetime::init(0, u64::MAX))
        .key_package_extensions(Extensions::empty())
        .leaf_node_extensions(Extensions::empty())
        .leaf_node_capabilities(get_dave_capabilities())
        .build(
            CIPHERSUITE,
            provider,
            signer,
            credential_with_key,
        )
        .expect("Failed to build KeyPackageBundle")
}
fn get_proposal_if_valid(message: ProcessedMessage) -> Option<QueuedProposal> {
    if !matches!(message.sender(), Sender::External(_)) {
        None
    }
    else if let ProcessedMessageContent::ProposalMessage(queued_proposal) = message.into_content() {
        match queued_proposal.proposal() {
            Proposal::Add(_) => Some(*queued_proposal),
            Proposal::Remove(_) => Some(*queued_proposal),
            _ => None
        }
    }
    else {
        None
    }
}

#[pyclass]
pub struct ProcessMessageResult {
    #[pyo3(get)]
    pub commit: Py<PyBytes>,

    #[pyo3(get)]
    pub welcome: Option<Py<PyBytes>>
}

#[pyclass]
pub struct DaveSession {
    user_id: u64,
    provider: OpenMlsRustCrypto,
    signature_keys: SignatureKeyPair,
    credential: Credential,
    key_package_bundle: KeyPackageBundle,
    mls_group: Option<MlsGroup>,
}

impl DaveSession {
    fn create_local_group(&self, group_id: GroupId, external_sender: ExternalSender) -> MlsGroup {
        let credential_with_key = CredentialWithKey {
            credential: self.credential.clone(),
            signature_key: self.signature_keys.public().into()
        };

        MlsGroup::builder()
            .with_group_id(group_id)
            .use_ratchet_tree_extension(true)
            .with_capabilities(get_dave_capabilities())
            .ciphersuite(CIPHERSUITE)
            .with_group_context_extensions(Extensions::single(Extension::ExternalSenders([external_sender].to_vec())))
            .expect("Failed to set local MLS group extensions")
            .with_leaf_node_extensions(Extensions::empty())
            .expect("Failed to set local MLS group leaf node extensions")
            .build(&self.provider, &self.signature_keys, credential_with_key)
            .expect("Failed to create local MLS group")
    }
}

#[pymethods]
impl DaveSession {
    #[new]
    fn new(user_id: &str) -> Self {
        let provider = OpenMlsRustCrypto::default();
        let parsed_user_id:u64 = user_id.parse().expect("Failed to parse user id to u64");
        let signature_keys = SignatureKeyPair::new(CIPHERSUITE.signature_algorithm())
            .expect("Error generating a signature key pair.");
        let credential:Credential = BasicCredential::new(parsed_user_id.to_be_bytes().to_vec()).into();
        let credential_with_key = CredentialWithKey {
            credential: credential.clone(),
            signature_key: signature_keys.public().into()
        };
        let kpb = build_key_package_bundle(&provider, &signature_keys, credential_with_key);

        signature_keys.store(provider.storage()).expect("Failed to store signature keys");

        Self {
            user_id: parsed_user_id,
            provider: provider,
            signature_keys: signature_keys,
            credential: credential,
            key_package_bundle: kpb,
            mls_group: None
        }
    }

    fn get_key_package_message(&self, py: Python<'_>) -> PyObject {
        let bytes_vec = self.key_package_bundle
            .key_package()
            .tls_serialize_detached()
            .expect("Failed to serialize key package");
        PyBytes::new(py, &bytes_vec).into()
    }

    fn init_mls_group(&mut self, external_sender_identity: &[u8], external_sender_signature: &[u8], welcome: &[u8]) { 
        //TODO (protocol check): external sender in welcome message must match this one
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
        let ratchet_tree = group_info
            .extensions()
            .ratchet_tree()
            .expect("Ratchet tree not found")
            .ratchet_tree()
            .clone();
        let staged_welcome = processed_welcome
            .into_staged_welcome(&self.provider, Some(ratchet_tree))
            .expect("Failed to stage welcome message");

        self.mls_group = Some(staged_welcome
            .into_group(&self.provider)
            .expect("Failed to create MlsGroup from staged welcome message")
        );
    }

    fn export_base_sender_key(&self, py: Python<'_>) -> PyObject {
        let k = self.mls_group
            .as_ref()
            .expect("MlsGroup not found - make sure to initialize the group with init_mls_group")
            .export_secret(self.provider.crypto(), "Discord Secure Frames v0", &self.user_id.to_le_bytes(), 16)
            .expect("Failed to export secret");
        PyBytes::new(py, &k).into()
    }

    // TODO: per the DAVE protocol, need to reject add proposals when user ID being added is not expected to be in the call,
    // according to clients_connect (11) and clients_disconnect (13) events
    // TODO: better function name to reflect the fact it only deals with proposal messages. In
    // fact, it currently only deals with *append* proposal messages
    fn process_message_in_local_group(&mut self, py: Python<'_>, message: &[u8], es_identity: &[u8], es_signature: &[u8]) -> Py<ProcessMessageResult> {
        let protocol_message = MlsMessageIn::tls_deserialize_exact(message)
            .expect("Failed to parse message")
            .try_into_protocol_message()
            .expect("Failed to convert incoming message to ProtocolMessage");
        let external_sender = ExternalSender::new(SignaturePublicKey::from(es_signature), BasicCredential::new(es_identity.to_vec()).into());
        let group_id = protocol_message.group_id().clone();

        let mut local_group = self.create_local_group(group_id, external_sender);

        let processed_message = local_group
            .process_message(&self.provider, protocol_message)
            .expect("Failed to process message with local MLS group");

        if let Some(queued_proposal) = get_proposal_if_valid(processed_message) {
            local_group.store_pending_proposal(self.provider.storage(), queued_proposal)
                .expect("Failed to store proposal");
        }

        let (commit_msg, welcome_msg, _group_info) = local_group.commit_to_pending_proposals(&self.provider, &self.signature_keys)
            .expect("Failed to create local group commit");

        let welcome = welcome_msg.as_ref().map(|msg| {
            match msg.body() {
                MlsMessageBodyOut::Welcome(welcome) => welcome,
                _ => unreachable!()
            }
        });

        Py::new(py,
                ProcessMessageResult {
                    commit: PyBytes::new(py, &commit_msg.tls_serialize_detached().expect("Failed to serialize commit")).into(),
                    welcome: welcome.map(|w| PyBytes::new(py, &w.tls_serialize_detached().expect("Failed to serialize welcome message")).into())
                }
        ).expect("Failed to create ProcessMessageResult")
    }
}

#[pymodule]
fn openmls_dave(_py: Python<'_>, m: &PyModule) -> PyResult<()> {
    m.add_class::<ProcessMessageResult>()?;
    m.add_class::<DaveSession>()?;
    Ok(())
}
