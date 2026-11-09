# otx-brand-samples

Find realistic brand-impersonation test data in [AlienVault OTX](https://otx.alienvault.com).

A detector for look-alike domains is only as good as the positives it is tested on, and made-up
examples (`examp1e-login.com`) test the detector you imagined, not the attacks people run. OTX
pulses are a free, community-curated record of real campaigns. This tool searches them for a brand,
pulls the domain, hostname and URL indicators from the pulses that mention it, and keeps the hosts
that look like the brand without being the brand. Every row says why it was kept, so a test set can
be balanced by kind instead of drowning in one easy pattern.

## Use

```sh
export OTX_API_KEY=...            # free: otx.alienvault.com, account settings
python3 brandsamples.py --brand examplebank --own examplebank.com,examplebank.co.uk --out samples.csv
```

| Flag | What |
|---|---|
| `--brand` | The token as it appears in hostnames (`examplebank`, not `Example Bank`) |
| `--own` | Domains the brand really owns; they and their subdomains are excluded |
| `--pulses` | Most pulses to read, most recently modified first (default 20) |
| `--since` | Only indicators created on or after this ISO date |
| `--live` | Write real URLs; the default is defanged (`hxxps://a[.]example[.]com`) |

A run prints a count per kind on stderr. The CSV columns are `host, url, kind, pulse_id,
pulse_name, first_seen`.

## How a host is kept

The first kind that matches wins.

| Kind | Rule | Example for `examplebank` |
|---|---|---|
| `label` | The brand is a whole DNS label | `examplebank.secure-portal.net` |
| `affix` | The brand is joined to other words by a hyphen | `examplebank-login.top`, `verify-examplebank.xyz` |
| `embedded` | The brand sits inside a longer label | `myexamplebankhelp.com` |
| `lookalike` | A label is one edit from the brand after homoglyph folding (`1`→`l`, `0`→`o`, `rn`→`m`) | `examp1ebank.co`, `exampelbank.info` |

Look-alikes are only tried for brands of five characters or more; below that, one edit matches
too much of the dictionary.

## What it is not

- **Not a liveness check.** A row is an indicator someone reported, possibly months ago. Check it
  before you count it as a live positive.
- **Not a verdict.** A pulse mentioning the brand is a lead. Community pulses are noisy, and a host
  in one is not proof of impersonation.
- **Not a crawler.** It never fetches the indicators themselves.

## Handle with care

The rows are real malicious infrastructure. Output is defanged by default; open nothing outside an
isolated browser or sandbox, and do not publish `--live` output.

## Test

```sh
python3 -m unittest -v
```

The OTX calls are tested against canned responses, so the suite runs offline and needs no key.

## License

MIT
