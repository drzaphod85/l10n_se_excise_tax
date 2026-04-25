# -*- coding: utf-8 -*-
import copy

from odoo import api, models, fields


class AccountTax(models.Model):
    _inherit = 'account.tax'

    amount_type = fields.Selection(
        selection_add=[('swedish_excise', 'Swedish Excise Tax (Weight/Unit)')],
        ondelete={'swedish_excise': 'set default'},
    )

    excise_type_id = fields.Many2one(
        'excise.tax.type',
        string="Linked Excise Type",
        help="Weight-based rate and per-unit cap used to compute the excise "
             "amount when amount_type is 'swedish_excise'.",
    )

    # Mirror fields so the tax form can show the current rate + cap of
    # the linked excise type without forcing the accountant to open a
    # second form. Both are `related` so edits are pushed back onto the
    # excise.tax.type record.
    excise_unit_basis_display = fields.Selection(
        related='excise_type_id.unit_basis',
        string="Unit Basis",
        readonly=True,
        help="Unit the rate is expressed per. Driven by the linked "
             "Excise Type. ``kg`` reads the product's excise weight; "
             "``liter`` reads its excise volume.",
    )
    excise_rate_display = fields.Float(
        related='excise_type_id.tax_rate',
        string="Rate (SEK / unit)",
        readonly=False,
        digits=(12, 2),
        help="Rate per unit_basis unit. SEK per kg for kg-based "
             "taxes (Kemikalieskatt), SEK per litre for liter-based "
             "taxes (Nikotinskatt e-liquid).",
    )
    excise_max_limit_display = fields.Float(
        related='excise_type_id.max_limit',
        string="Max Limit per Unit (SEK)",
        readonly=False,
        digits=(12, 2),
        help="Per-unit cap. Used by Kemikalieskatt only; 0 for any "
             "non-capped excise type.",
    )

    # Posting Setup summary – surfaced on the excise block of the tax
    # form so an accountant can see at a glance which GL account and
    # Skatteverket tags this tax is wired to, without scrolling to the
    # Definition tab where the full repartition grid lives.
    excise_posting_account_id = fields.Many2one(
        'account.account',
        string="Posting Account",
        compute='_compute_excise_posting_summary',
        help="Liability account where the excise tax amount is booked. "
             "Derived from the first 'tax'-type invoice repartition line.",
    )
    excise_posting_tags = fields.Char(
        string="Reporting Tags",
        compute='_compute_excise_posting_summary',
        help="Skatteverket excise-declaration tags attached to this tax, "
             "aggregated across invoice and refund repartition lines.",
    )

    @api.depends(
        'invoice_repartition_line_ids.account_id',
        'invoice_repartition_line_ids.tag_ids',
        'invoice_repartition_line_ids.repartition_type',
        'refund_repartition_line_ids.tag_ids',
    )
    def _compute_excise_posting_summary(self):
        for tax in self:
            tax_rep = tax.invoice_repartition_line_ids.filtered(
                lambda r: r.repartition_type == 'tax'
            )[:1]
            tax.excise_posting_account_id = tax_rep.account_id or False
            all_tags = (tax.invoice_repartition_line_ids.tag_ids
                        | tax.refund_repartition_line_ids.tag_ids)
            tax.excise_posting_tags = ', '.join(all_tags.mapped('name')) or False

    # ------------------------------------------------------------------
    # Excise computation helpers
    # ------------------------------------------------------------------
    def _get_excise_unit_amount(self, weight=0.0, reduction_ratio=1.0,
                                volume=0.0, pieces=0.0):
        """Return the excise amount for a SINGLE unit of product.

        Dispatches on ``self.excise_type_id.unit_basis``:

        * ``'kg'``    — weight × rate, capped at ``max_limit``,
                       multiplied by ``reduction_ratio`` if the
                       excise type has the Kemikalieskatt-style
                       reduction.
        * ``'liter'`` — volume × rate (no cap, no reduction).
        * ``'pcs'``   — pieces × rate (no cap, no reduction).
                       ``pieces`` is the number of countable units
                       inside one product unit (e.g. 20 cigarettes
                       per pack).

        Future ``unit_basis`` values (``'tonne'``, ``'liter_pure'``,
        ``'m3'``, …) get their own branches as the corresponding
        Phase-3/4 taxes are implemented.

        :param float weight:          Snapshot weight (kg) — kg basis.
        :param float volume:          Snapshot volume (L) — liter basis.
        :param float pieces:          Snapshot piece count — pcs basis.
        :param float reduction_ratio: 1.0 / 0.5 / 0.1 — kg basis only,
                                       only when ``has_reduction_levels``
                                       is True on the excise type.
        :return float: Per-unit excise amount in company currency.
        """
        self.ensure_one()
        excise = self.excise_type_id
        if not excise:
            return 0.0
        basis = excise.unit_basis or 'kg'

        if basis == 'kg':
            if weight <= 0.0:
                return 0.0
            raw_tax = weight * excise.tax_rate
            if excise.max_limit > 0 and raw_tax > excise.max_limit:
                raw_tax = excise.max_limit
            # Reduction is Kemikalieskatt-specific. Excise types that
            # don't enable ``has_reduction_levels`` (e.g. Nikotinskatt
            # 'Övriga produkter' which is also kg-based) ignore the
            # ratio entirely — multiplying by 1.0 keeps the snapshot
            # field on the line harmless even if a user accidentally
            # set a reduction on the product.
            if excise.has_reduction_levels:
                return raw_tax * (reduction_ratio or 1.0)
            return raw_tax

        if basis == 'liter':
            if volume <= 0.0:
                return 0.0
            return volume * excise.tax_rate

        if basis == 'pcs':
            if pieces <= 0.0:
                return 0.0
            return pieces * excise.tax_rate

        # Unknown / not-yet-supported basis — return 0 so that
        # adding a new selection value before its computation
        # branch lands doesn't silently miscompute. The value is
        # stored in tax_data['tax_amount']=0 and the cascade still
        # fires (with 0), which is harmless.
        return 0.0

    # ------------------------------------------------------------------
    # New-engine hook (Odoo 17+ tax engine)
    # ------------------------------------------------------------------
    def _eval_tax_amount_fixed_amount(self, batch, raw_base, evaluation_context):
        """Extend the fixed-amount evaluator so it also handles our
        custom ``amount_type='swedish_excise'``.

        The per-line snapshot (``excise_weight`` / ``excise_volume``
        / ``excise_reduction_ratio``) is propagated through the tax
        recordset's context by the overrides on ``sale.order.line``
        / ``account.move.line`` — they call
        ``base_line['tax_ids'].with_context(excise_line_vals=...)``,
        and that context is carried here on ``self``.

        Only this single pass is overridden, on purpose: returning a
        value from multiple passes makes the engine's cascade-into-
        next-tax-base logic fire more than once for the same tax,
        which would over-augment the VAT base.

        The actual unit-basis dispatch happens inside
        ``_get_excise_unit_amount``; this hook just unpacks the
        per-line snapshot from context and applies the line's
        quantity and sign.
        """
        if self.amount_type == 'swedish_excise':
            excise_vals = self.env.context.get('excise_line_vals') or {}
            unit_amount = self._get_excise_unit_amount(
                weight=excise_vals.get('excise_weight', 0.0) or 0.0,
                volume=excise_vals.get('excise_volume', 0.0) or 0.0,
                pieces=excise_vals.get('excise_pieces', 0.0) or 0.0,
                reduction_ratio=(
                    excise_vals.get('excise_reduction_ratio', 1.0) or 1.0
                ),
            )
            sign = -1 if evaluation_context.get('price_unit', 0.0) < 0.0 else 1
            quantity = evaluation_context.get('quantity', 0.0) or 0.0
            return sign * quantity * unit_amount
        return super()._eval_tax_amount_fixed_amount(
            batch, raw_base, evaluation_context,
        )

    # ------------------------------------------------------------------
    # tax_totals display filter
    # ------------------------------------------------------------------
    # The companion overrides on ``account.move`` and ``sale.order``
    # call this helper after ``super()._compute_tax_totals()`` so both
    # models share the same folding / hiding logic.  It mutates a copy
    # of the ``tax_totals`` JSON served to the ``account_tax_totals``
    # widget; the underlying tax lines and postings are untouched.
    # ------------------------------------------------------------------
    @api.model
    def _l10n_se_excise_postprocess_tax_totals(
        self, totals, *, fold_excise=False,
    ):
        """Return ``totals`` with the excise group folded into the
        Untaxed Amount when ``fold_excise`` is True.

        * ``fold_excise`` → drop the excise tax group from the visible
          breakdown and bump the Untaxed Amount by the same amount
          so the customer sees a coherent "Untaxed (X+E) → VAT →
          Total" block. The VAT group stays visible in every case
          because the VAT base is ``X+E`` (excise has
          ``include_base_amount=True``) and the law requires the
          totals block to disclose the VAT amount separately.

        The per-line presentation is a separate concern:
        ``sale.order.line`` / ``account.move.line`` expose
        ``l10n_se_display_price_subtotal`` and the QWeb inherits in
        ``views/report_templates.xml`` render it instead of
        ``price_subtotal`` on the Amount column when fold is on.
        ``hide_vat_column_on_documents`` is handled purely in the
        QWeb inherits — it does not touch ``tax_totals``.

        The method tolerates both tax_totals shapes seen across
        Odoo 17 / 18 / 19: the newer ``subtotals[*].tax_groups[*]``
        nesting and the older ``groups_by_subtotal[name][*]`` mapping.

        Implementation note on subtotal pruning: when cascading taxes
        (excise with ``include_base_amount=True`` + VAT) are active,
        Odoo builds two subtotal "steps", one per tax stage. Removing
        the excise group empties the first step; left in place that
        empty step still renders as a phantom "Subtotal:" row in the
        widget with no taxes after it, which made the VAT row look
        like it had vanished. We therefore drop empty subtotal
        entries altogether so the next populated subtotal (containing
        VAT) is what the widget renders immediately after Untaxed
        Amount.
        """
        if not isinstance(totals, dict) or not fold_excise:
            return totals

        excise_group = self.env.ref(
            'l10n_se_excise_tax.tax_group_excise',
            raise_if_not_found=False,
        )
        excise_group_id = excise_group.id if excise_group else None
        if not excise_group_id:
            return totals

        def _is_excise(group_dict):
            gid = group_dict.get('id') or group_dict.get('tax_group_id')
            return gid == excise_group_id

        def _amount(group_dict):
            # Pick whichever amount key the current Odoo version uses.
            return (
                group_dict.get('tax_amount_currency')
                or group_dict.get('tax_amount')
                or group_dict.get('tax_group_amount')
                or 0.0
            )

        new_totals = copy.deepcopy(totals)
        folded_amount = 0.0

        # Keys Odoo 19's tax_totals widget reads for the displayed
        # base / tax / total amounts. The empirically-observed JSON
        # uses ``base_amount`` / ``tax_amount`` / ``total_amount``
        # plus the matching ``_currency`` variants. Earlier Odoo
        # versions used ``amount_untaxed`` / ``amount_tax`` /
        # ``amount_total``, which we keep in the lists below as a
        # fallback for compatibility.
        BASE_KEYS = ('base_amount', 'base_amount_currency',
                     'amount_untaxed')
        TAX_KEYS = ('tax_amount', 'tax_amount_currency',
                    'amount_tax')

        # Newer shape: subtotals[*].tax_groups[*].
        # We rebuild the subtotals list, dropping entries whose
        # tax_groups become empty after filtering — see docstring.
        raw_subtotals = new_totals.get('subtotals')
        if isinstance(raw_subtotals, list):
            new_subtotals = []
            for subtotal in raw_subtotals:
                kept = []
                subtotal_folded = 0.0
                for group in subtotal.get('tax_groups') or []:
                    if _is_excise(group):
                        amount = _amount(group)
                        folded_amount += amount
                        subtotal_folded += amount
                        continue
                    kept.append(group)
                if 'tax_groups' in subtotal:
                    subtotal['tax_groups'] = kept
                # Bump this subtotal's "base" by the folded excise
                # and reduce its "tax" by the same amount, so that
                # base + tax (the running total at this subtotal
                # level) stays unchanged. The displayed
                # "Summa exkl. moms" row is rendered from
                # ``subtotal.base_amount[_currency]``; without this
                # bump it stays at the pre-excise net subtotal.
                if subtotal_folded:
                    for key in BASE_KEYS:
                        if key in subtotal:
                            subtotal[key] = subtotal[key] + subtotal_folded
                    for key in TAX_KEYS:
                        if key in subtotal:
                            subtotal[key] = subtotal[key] - subtotal_folded
                    # Drop pre-formatted strings so the widget
                    # re-renders from the bumped numeric fields.
                    for stale in ('formatted_amount', 'formatted_base_amount',
                                  'formatted_base_amount_currency',
                                  'formatted_tax_amount',
                                  'formatted_tax_amount_currency'):
                        subtotal.pop(stale, None)
                if kept:
                    new_subtotals.append(subtotal)
            new_totals['subtotals'] = new_subtotals

        # Older shape: groups_by_subtotal[name] = [groups].
        # Same pruning logic; empty subtotal buckets get removed.
        gbs = new_totals.get('groups_by_subtotal')
        if isinstance(gbs, dict):
            count_here = not isinstance(raw_subtotals, list)
            for name, groups in list(gbs.items()):
                kept = []
                for group in groups:
                    if _is_excise(group):
                        if count_here:
                            folded_amount += _amount(group)
                        continue
                    kept.append(group)
                if kept:
                    gbs[name] = kept
                else:
                    del gbs[name]

        # Bump the top-level base by the folded excise and reduce
        # the top-level tax by the same amount. ``total_amount`` /
        # ``amount_total`` are intentionally NOT touched — they were
        # already correct (excise was always part of the total) and
        # keeping them constant is what makes the widget's math
        # consistent: base + tax = total still holds.
        if folded_amount:
            for key in BASE_KEYS:
                if key in new_totals:
                    new_totals[key] = new_totals[key] + folded_amount
            for key in TAX_KEYS:
                if key in new_totals:
                    new_totals[key] = new_totals[key] - folded_amount
            for stale in ('formatted_amount_untaxed',
                          'formatted_base_amount',
                          'formatted_base_amount_currency',
                          'formatted_tax_amount',
                          'formatted_tax_amount_currency'):
                new_totals.pop(stale, None)

        return new_totals
