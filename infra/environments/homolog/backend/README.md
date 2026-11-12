# Protected remote state bucket

The Phase 4 state bucket is `togglemaster-tfstate-group119`, a new bucket with its own `togglemaster/phase4/homolog/backend.tfstate` key. The Phase 3 bucket (`togglemaster-tfstate-group76`) is not reused and is not managed by this root; it still holds the Phase 3 states and must not be renamed or deleted without explicit authorization.

Bootstrap used for this environment: create the private/versioned bucket with OCI CLI, initialize this root with its ignored backend.hcl, and import the bucket with `terraform import oci_objectstorage_bucket.state 'n/<namespace>/b/<bucket>'`. Verify a no-change plan. This keeps authoritative state remote from the first Terraform operation and avoids generating local bootstrap state. The bucket is subsequently managed by this root.

Core and platform initialize directly against this bucket with their own Object Storage keys. Never commit backend.hcl, real tfvars, kubeconfigs, state or saved plans. The bucket has prevent_destroy and is retained during application teardown; confirm residual objects/costs afterward.
