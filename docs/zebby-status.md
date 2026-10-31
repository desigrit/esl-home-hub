# Zebby status

Open **Zebby** in RonHub for service health and successful credit purchases.
The chart offers 7-, 30- and 90-day views. Hover a day or use the arrow keys
to inspect its count. Dates use Pacific time.

## What is checked

- **Azure:** the live credit service responds to `/health` over public HTTPS.
- **Stripe:** its authenticated Checkout API responds to a read-only request.
- **Supabase:** the purchase ledger can be read and reconciled.

A transaction is one paid, live Zebby credit purchase. The date comes from the
ledger entry that added credits, rather than when checkout was opened. Duplicate
webhooks, unpaid sessions and test checkouts do not add transactions. A refunded
purchase remains in this historical purchase count.

Checks run every minute through `ronhub-zebby-status.timer`. **Refresh status**
starts an additional check without blocking other hub pages. Checks older than
150 seconds become unverified. A failed check keeps the previous purchase totals
and their original timestamp, with a visible stale-data message.

## Connection

Stripe and Supabase keys stay in `/etc/zebby/credits.env` on Azure. The Pi receives
only service results, an all-time count and daily totals through a dedicated SSH
key. The browser never receives API keys, payment IDs, customer names or emails.

Install `tools/zebby_reader.py` as a root-owned, non-writable file at
`/usr/local/lib/ronhub/zebby_reader.py` on the credit-service VM. A dedicated
`ronhub-zebby` account uses an authorized key restricted to this command:

```text
restrict,command="/usr/bin/sudo -n /usr/bin/python3 /usr/local/lib/ronhub/zebby_reader.py" PUBLIC_KEY
```

Give that account only this sudo command, and validate the file with `visudo`:

```text
ronhub-zebby ALL=(root) NOPASSWD: /usr/bin/python3 /usr/local/lib/ronhub/zebby_reader.py
```

Store the private SSH key and pinned Azure host key under `.runtime/ronhub/` on
the Pi. Add a `zebby` section to its existing `.runtime/ronhub/config.json`:

```json
{
  "zebby": {
    "host": "ronhub-zebby@YOUR_VM_ADDRESS",
    "key_path": "/home/ronhub/esl_hub/.runtime/ronhub/zebby_reader_key",
    "known_hosts": "/home/ronhub/esl_hub/.runtime/ronhub/zebby_known_hosts"
  }
}
```

Install `tools/ronhub-zebby-status.service` and `.timer` in `/etc/systemd/system/`,
then run:

```sh
sudo systemctl daemon-reload
sudo systemctl enable --now ronhub-zebby-status.timer
sudo systemctl start ronhub-zebby-status.service
```

Check the timer and the three status values in its journal. No payment or
database mutation is used to test health. Collection has fixed request deadlines,
rejects redirects, pins the SSH host key and refuses partial paginated totals.
Source updates to the reader must be installed on Azure as well as the Pi.

To remove this connection, stop and disable the timer and remove its SSH key
from the dedicated Azure account. Existing payment processing is independent of
this reader.
