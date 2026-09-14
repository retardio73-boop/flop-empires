# Season 0 referee offline verification

Two separate processes recovered the same exact referee DID through Windows
DPAPI CurrentUser. Each process created a fresh 32-byte random challenge, signed
it, and verified the Ed25519 signature locally.

- DID: `did:key:z6MkkvjnHUEz5qmMHXZJiTg8BFSjm3KVqZtueNUMdp1FqMpx`
- Pass 1: verified
- Pass 2: verified
- Fallback or regeneration: no
- Private material printed or logged: no
- Network writes: 0
