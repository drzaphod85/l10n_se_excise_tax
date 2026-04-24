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
    excise_rate_display = fields.Float(
        related='excise_type_id.tax_rate',
        string="Rate (SEK/kg)",
        readonly=False,
        digits=(12, 2),
    )
    excise_max_limit_display = fields.Float(
        related='excise_type_id.max_limit',
        string="Max Limit per Unit (SEK)",
        readonly=False,
        digits=(12, 2),
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
    # Excise computation helper
    # ------------------------------------------------------------------
    def _get_excise_unit_amount(self, weight, reduction_ratio):
        """Return the excise amount for a SINGLE unit of product.

        :param float weight:          Snapshot net weight (kg) for excise.
        :param float reduction_ratio: 1.0 / 0.5 / 0.1 reduction factor.
        :return float: Per-unit excise amount in company currency (SEK).
        """
        self.ensure_one()
        excise = self.excise_type_id
        if not excise or weight <= 0.0:
            return 0.0
        raw_tax = weight * excise.tax_rate
        if excise.max_limit > 0 and raw_tax > excise.max_limit:
            raw_tax = excise.max_limit
        return raw_tax * (reduction_ratio or 1.0)

    # ------------------------------------------------------------------
    # New-engine hook (Odoo 17+ tax engine)
    # ------------------------------------------------------------------
    def _eval_tax_amount_fixed_amount(self, batch, raw_base, evaluation_context):
        """Extend the ascending-pass fixed-amount evaluator so it also
        handles our custom ``amount_type='swedish_excise'``.

        The per-line snapshot (``excise_weight`` / ``excise_reduction_ratio``)
        is propagated through the tax recordset's context by the overrides
        on ``sale.order.line`` and ``account.move.line`` — they call
        ``base_line['tax_ids'].with_context(excise_line_vals=...)``, and
        that context is carried here on ``self``.
        """
        if self.amount_type == 'swedish_excise':
            excise_vals = self.env.context.get('excise_line_vals') or {}
            weight = excise_vals.get('excise_weight', 0.0) or 0.0
            reduction = excise_vals.get('excise_reduction_ratio', 1.0) or 1.0
            unit_amount = self._get_excise_unit_amount(weight, reduction)
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
        self, totals, *, fold_excise=False, hide_vat=False,
    ):
        """Return ``totals`` filtered according to the two display
        flags that the caller has derived for the current document.

        * ``fold_excise`` → drop the excise tax group from the visible
          breakdown and add its amount to the Untaxed Amount line so
          the numbers still add up.
        * ``hide_vat`` → drop every non-excise tax group (typically
          VAT / moms) from the visible breakdown. The total is left
          as-is because VAT is still charged and posted — only the
          *row* disappears.

        The two flags are passed in by the caller rather than read
        from the company here, because ``sale.order`` and
        ``account.move`` have different policies: a final invoice
        must always show the VAT row per Mervärdesskattelagen 11 kap.
        8 §, while quotations have no such disclosure requirement.

        The method tolerates both tax_totals shapes seen across
        Odoo 17 / 18 / 19: the newer ``subtotals[*].tax_groups[*]``
        nesting and the older ``groups_by_subtotal[name][*]`` mapping.
        """
        if not isinstance(totals, dict):
            return totals
        if not (fold_excise or hide_vat):
            return totals

        excise_group = self.env.ref(
            'l10n_se_excise_tax.tax_group_excise',
            raise_if_not_found=False,
        )
        excise_group_id = excise_group.id if excise_group else None

        def _is_excise(group_dict):
            gid = group_dict.get('id') or group_dict.get('tax_group_id')
            return excise_group_id and gid == excise_group_id

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

        # Newer shape: subtotals[*].tax_groups[*].
        for subtotal in new_totals.get('subtotals') or []:
            kept = []
            for group in subtotal.get('tax_groups') or []:
                if fold_excise and _is_excise(group):
                    folded_amount += _amount(group)
                    continue
                if hide_vat and not _is_excise(group):
                    continue
                kept.append(group)
            if 'tax_groups' in subtotal:
                subtotal['tax_groups'] = kept

        # Older shape: groups_by_subtotal[name] = [groups].
        gbs = new_totals.get('groups_by_subtotal')
        if isinstance(gbs, dict):
            for name, groups in list(gbs.items()):
                kept = []
                for group in groups:
                    if fold_excise and _is_excise(group):
                        folded_amount += _amount(group)
                        continue
                    if hide_vat and not _is_excise(group):
                        continue
                    kept.append(group)
                gbs[name] = kept

        # If we folded excise into untaxed, bump the visible Untaxed
        # Amount so the customer-facing numbers still add up (total
        # stays identical because excise was already included in it).
        if fold_excise and folded_amount:
            if 'amount_untaxed' in new_totals:
                new_totals['amount_untaxed'] = (
                    new_totals['amount_untaxed'] + folded_amount
                )
            # Drop stale pre-formatted values so the widget re-renders
            # the numeric field we just updated.
            new_totals.pop('formatted_amount_untaxed', None)

            for subtotal in new_totals.get('subtotals') or []:
                for key in ('amount', 'base_amount', 'base_amount_currency'):
                    if key in subtotal:
                        subtotal[key] = subtotal[key] + folded_amount
                subtotal.pop('formatted_amount', None)
                subtotal.pop('formatted_base_amount', None)
                break  # only the first (Untaxed Amount) subtotal

        return new_totals
