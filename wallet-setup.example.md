# wallet-setup.md (copy to wallet-setup.md — gitignored)

## Agent EOA

```
0xYOUR_EOA_ADDRESS
```

## Networks

| Chain | Chain ID | RPC |
|-------|----------|-----|
| Base | 8453 | https://mainnet.base.org |
| Optimism | 10 | https://mainnet.optimism.io |
| Arbitrum | 42161 | https://arb1.arbitrum.io/rpc |

## USDC (native)

- Base: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- Optimism: `0x0b2C639c5338137C4aa58B0cAe1a9CfBe376e89Fd`
- Arbitrum: `0xaf88d065e77c8cC2239327C5EDb3A432268e5831`

## Sports AMM V2 (verify at https://contracts.overtime.io/)

- Base: `0xa1ead27ebbd90b8ef385f264cc66ba4c96767fdf`
- Optimism: `0xFb4e4811C7A811E098A556bD79B64c20b479E431`
- Arbitrum: _(verify deployment)_

## Phase 0 transaction log

| Step | Tx hash | Amount | Network |
|------|---------|--------|---------|
| Test USDC | | 5.81 USDC | Base |
| Fund 1 | | | |
| Test bet Base | | ~3 USDC | Base |
| Test bet OP | | | Optimism |
| Test bet Arb | | | Arbitrum |
| Bridge OP→Base | | 10 USDC | Across |

## Bridge benchmark (measured)

- Route: Optimism → Base, 10 USDC
- Time: 2 seconds
- Fee: $0.004 (0.04%)

## VPS

- Provider: Vultr Amsterdam
- IP: 78.141.218.15
- SSH: `ssh overtime-agent`

## Telegram

- Bot: @your_bot
- Chat ID: (from getUpdates)
- Token: stored in 1Password + `/etc/agent/env`
