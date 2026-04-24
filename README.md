# Swedish Excise Tax (`l10n_se_excise_tax`)

Odoo 19 module that adds Swedish excise-tax handling to quotations, sales
orders and invoices. The first-phase scope is **Chemical Tax
(Kemikalieskatt)** on electronics and major appliances, but the design is
intended to generalise to every EU excise duty that is charged before VAT.

* **Version:** 19.0.1.0.0
* **License:** LGPL-3
* **Author:** Lasse Larsson
* **Category:** Accounting / Localizations
* **Depends on:** `account`, `product`, `sale`

---

## Why this module exists

Swedish excise taxes (punktskatter) are levied on specific goods and are
calculated **before** VAT; VAT is then charged on the sum of the line
subtotal and the excise amount. Standard Odoo tax types
(`percent` / `fixed` / `division`) cannot express the Swedish Chemical
Tax rule, which is:

    excise_per_unit = min(net_weight_kg * rate_sek_per_kg, max_limit_sek)

with an optional reduction of 50 % or 90 % per product.

This module plugs a new `amount_type = 'swedish_excise'` into Odoo's
rewritten tax engine, adds the per-product snapshot data the formula
needs, and wires the result into the standard VAT base so the final
invoice totals are correct end-to-end.

---

## Features

* **Excise Tax Types** – a lightweight master data model
  (`excise.tax.type`) holding the per-kg rate and the maximum per-unit
  cap. Two demo types ship with the module: *Electronics (High Rate)*
  at 114 SEK/kg and *Major Appliances (Low Rate)* at 11 SEK/kg, both
  capped at 562 SEK/unit.
* **Product configuration** – on each product template you can flag it
  as excise-taxable, pick an excise type, enter the excise weight, and
  select a reduction level (0 %, 50 % or 90 %).
* **New tax kind** – `amount_type = 'swedish_excise'` on `account.tax`,
  with a Many2one to the excise type and related inline-editable
  rate/cap fields.
* **Tax-engine integration** – overrides the new (Odoo 17+)
  `_eval_tax_amount_fixed_amount` hook so the engine can actually
  produce a non-zero amount for our custom type. A per-line snapshot
  (weight + reduction factor) is propagated through the tax recordset
  via context.
* **VAT compounding** – the excise tax uses `include_base_amount=True`,
  so VAT is computed on `(line subtotal + excise)` as required by
  Skatteverket.
* **Tax totals ordering** – dedicated `account.tax.group` with a low
  `sequence` so the excise row appears immediately *before* VAT in the
  tax totals widget on quotations, orders and invoices.
* **Snapshot on the lines** – both `sale.order.line` and
  `account.move.line` store the excise weight and reduction ratio that
  were in effect when the line was created, so later edits on the
  product template don't retroactively change confirmed orders or
  posted invoices.
* **Swedish posting wiring** – explicit invoice/refund repartition with
  Skatteverket reporting tags and automatic binding of the first
  available BAS liability account (2616 → 2615 → 2640 → 2980) per
  company via a `post_init_hook`.
* **Posting Setup summary** – the tax form shows, read-only, which GL
  account and which Skatteverket tags the tax is currently wired to,
  without having to scroll into the Definition tab.

---

## Architecture at a glance

```
   Product (is_excise_taxable, excise_tax_type_id,
            net_weight_excise, excise_reduction)
            │
            │  onchange  →  snapshot copied to the line
            ▼
   sale.order.line  /  account.move.line
       excise_weight, excise_reduction_ratio
            │
            │  _prepare_base_line_for_taxes_computation
            │     └─ base_line['tax_ids'] = tax_ids.with_context(
            │                                   excise_line_vals={...})
            ▼
   account.tax (amount_type = 'swedish_excise',
                excise_type_id, include_base_amount=True,
                tax_group_id = Swedish Excise Tax)
            │
            │  _eval_tax_amount_fixed_amount
            │     └─ reads excise_line_vals from self.env.context,
            │        returns quantity * min(weight*rate, cap) * reduction
            ▼
   Tax totals widget (excise row ──► VAT on base+excise)
            │
            ▼
   Invoice repartition lines
       base line  → tag: +/-Kemikalieskatt – Underlag
       tax  line  → tag: +/-Kemikalieskatt – Skatt att betala,
                    account_id = BAS 2616/2615/2640/2980,
                    use_in_tax_closing = True
```

---

## Installation

1. Drop the module in an Odoo 19 addons path.
2. Update the app list and install **Swedish Excise Tax (Chemical Tax)**.

The `post_init_hook` runs once at install and binds the first BAS
liability account it finds on each company
(`2616 → 2615 → 2640 → 2980`) to the tax-type repartition lines. If
none exist, it logs a notice and the accountant is expected to assign
the account manually on the tax form.

### Updating an existing install

The preferred command is:

```bash
odoo -c /etc/odoo/odoo.conf -u l10n_se_excise_tax
```

Do **not** use `-i` on an already-installed database unless you also
want to re-run the post-init hook and rewrite the Python structure.

> ⚠️ **`noupdate="1"` caveat.** `data/excise_tax_data.xml` is declared
> `noupdate="1"` so that accountant-side customisations survive
> upgrades. The side-effect is that existing databases will **not**
> receive new/changed repartition lines, tags or tax-group changes on
> a plain `-u`. For existing test databases, pick one of:
>
> * Temporarily flip the file to `noupdate="0"` for a single upgrade,
>   then flip it back.
> * Write a one-shot migration script in `migrations/`.
> * Recreate the two `tax_chemical_*` records manually in the UI.

---

## Configuration

### Excise Tax Types

*Accounting → Configuration → Excise Tax Types*

Maintain the rate (SEK/kg) and max cap per excise type. Confirmed
orders and posted invoices are immune to later rate changes because
they carry a snapshot.

### Products

On the product template, enable **Excise Taxable** and fill in:

* **Excise Tax Type** – the rate/cap row to use
* **Excise Tax Weight (kg)** – the weight that drives the calculation
* **Reduction Level** – 0 % (full), 50 % or 90 %

Finally, add the matching `account.tax` (e.g. *Chemical Tax
(Electronics)* — internal name `CHEM E`) to the product's **Customer
Taxes** alongside VAT.

### Tax form

Each excise tax shows:

* Linked **Excise Type** (with inline-editable rate and cap).
* **Posting Setup** block — read-only summary of the GL account and
  Skatteverket tags derived from the Definition tab.

### Per-line overrides

On the sale order and invoice line, `Excise Weight` and
`Excise Reduction Ratio` are editable (hidden columns by default, shown
via the optional-column selector). This lets the accountant tweak a
specific document without changing the product master.

---

## Posting & reporting

* **GL account** – automatically bound to the first available BAS
  liability account per company: `2616` (preferred, *Kemikalieskatt
  att betala*), `2615`, `2640` (*Övrig punktskatt*) or `2980`
  (*Övriga skatteskulder*).
* **Skatteverket tags** – four `account.account.tag` records scoped to
  Sweden (`country_id = base.se`, `applicability = taxes`), following
  Odoo's `+`/`-` convention so refunds reverse the sign automatically:
  `±Kemikalieskatt – Underlag`, `±Kemikalieskatt – Skatt att betala`.
* **Tax closing** – the tax repartition lines are flagged
  `use_in_tax_closing = True`, so the amounts feed the standard Odoo
  tax closing entry.

---

## Upgrade / development commands

```bash
# Restart + update the module (safe default)
odoo -c /etc/odoo/odoo.conf -u l10n_se_excise_tax

# Re-install (runs post_init_hook again; loses data stored in
# noupdate="1" records on an existing DB — use with care)
odoo -c /etc/odoo/odoo.conf -i l10n_se_excise_tax

# Tail logs
journalctl -u odoo -f
```

---

## Module layout

```
l10n_se_excise_tax/
├── __init__.py                 # imports models + post_init_hook
├── __manifest__.py
├── hooks.py                    # BAS-account binder (post_init_hook)
├── README.md
├── data/
│   └── excise_tax_data.xml     # tax group, tags, excise types, taxes
├── models/
│   ├── __init__.py
│   ├── account_move_line.py    # invoice-line snapshot + tax-engine hook
│   ├── account_tax.py          # swedish_excise amount type + engine hook
│   ├── excise_tax.py           # excise.tax.type + product.template fields
│   └── sale_order_line.py      # order-line snapshot + tax-engine hook
├── security/
│   └── ir.model.access.csv
└── views/
    ├── account_move_views.xml  # invoice line excise columns
    ├── account_tax_views.xml   # tax form: excise block + Posting Setup
    ├── product_views.xml       # product template + excise.tax.type views
    └── sale_order_views.xml    # SO line excise columns
```

---

## Known limits / roadmap

* **Scope.** Only Swedish Chemical Tax is shipped out of the box. The
  engine is generic (weight × rate, capped, optional reduction) and
  should cover most weight- or unit-based excise duties in the EU. To
  add a new country/duty:
  1. Add `excise.tax.type` records with the country-specific rate/cap.
  2. Add `account.account.tag` records with `country_id` set to the
     target country and the local reporting box codes.
  3. Add `account.tax` records pointing at the new excise type and
     tags, in a country-scoped data file.
  4. Add the target country's liability account code(s) to
     `hooks._CANDIDATE_CODES` (or refactor the hook to read them from
     a per-country mapping).
* **Migration of existing databases.** Because of `noupdate="1"`, new
  releases won't retroactively fix repartition lines on already-
  installed DBs. A future release should ship a `migrations/` script.
* **Multi-company.** The hook searches the BAS account in each
  company's chart separately, but the data-file tags are global (they
  carry `country_id = base.se`). That is fine for SE-only tenants and
  will need country scoping once non-SE data is added.
* **Tests.** The current test coverage is manual (SO → invoice round
  trip). A future release should add an automated
  `tests/test_excise_chemical.py` covering weight × rate, cap,
  reduction, VAT compounding and refund sign flipping.

---

## Acknowledgements

Developed against Odoo 19. Designed to play nicely with the Swedish
Accounting localization (`l10n_se*`) and with Odoo's tax-closing and
tax-reports workflow. Contributions extending the module to other EU
excise regimes are welcome.
