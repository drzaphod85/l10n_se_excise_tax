# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ExciseTaxDefault(models.Model):
    """A rule that says "products in this category (or all products)
    should default to this excise tax with these settings".

    Defaults are applied to a product when:

    - It's first set as ``is_excise_taxable`` and no excise type is
      picked yet (the per-product onchange will offer the matching
      default).
    - The user runs the ``Apply Excise Defaults`` server action on
      a selection of products (catches existing products that
      pre-date the rule).

    Defaults are looked up in two passes: first by the product's
    own ``categ_id``, and if no rule matches, again with no category
    filter (the "all products" fallback). Within either pass, rules
    are ordered by ``sequence``, so multiple rules under the same
    category can be prioritised.

    The rule covers both the ``account.tax`` to add to the
    product's Customer Taxes and the per-product reduction level
    (Kemikalieskatt 0 / 50 / 95 %), so accountants only have to
    fill the rule once and the product gets a complete
    configuration.
    """

    _name = 'excise.tax.default'
    _description = 'Default Excise Tax Rule'
    _order = 'sequence, id'

    name = fields.Char(
        string="Rule Name",
        required=True,
        translate=True,
        help="Free-form label shown in the rules list. e.g. "
             "'Electronics — high-rate Kemikalieskatt'.",
    )
    sequence = fields.Integer(
        default=10,
        help="Used to order rules that share the same scope. "
             "Lower number = applied first.",
    )
    active = fields.Boolean(
        default=True,
        help="Untick to keep the rule on file but stop it from "
             "applying to new products.",
    )

    # ------------------------------------------------------------------
    # Scope — which products the rule applies to.
    # ------------------------------------------------------------------
    product_category_id = fields.Many2one(
        'product.category',
        string="Product Category",
        ondelete='cascade',
        help="Apply this default only to products whose Internal "
             "Category matches. Leave empty to apply to ALL products "
             "as a fallback. Category-specific rules win over the "
             "all-products fallback.",
    )

    # ------------------------------------------------------------------
    # What the rule sets on matching products.
    # ------------------------------------------------------------------
    excise_tax_id = fields.Many2one(
        'account.tax',
        string="Default Excise Tax",
        required=True,
        ondelete='cascade',
        domain=[('amount_type', '=', 'swedish_excise')],
        help="The swedish_excise account.tax to add to a matching "
             "product's Customer Taxes. The product's Excise Type "
             "is set automatically to this tax's linked Excise Type.",
    )
    excise_tax_type_id = fields.Many2one(
        related='excise_tax_id.excise_type_id',
        string="Excise Type",
        readonly=True,
    )
    excise_unit_basis = fields.Selection(
        related='excise_tax_id.excise_type_id.unit_basis',
        string="Unit Basis",
        readonly=True,
    )
    excise_has_reduction_levels = fields.Boolean(
        related='excise_tax_id.excise_type_id.has_reduction_levels',
        string="Has Reduction Levels",
        readonly=True,
    )
    excise_reduction = fields.Selection(
        [
            ('0', 'No Reduction (100%)'),
            ('50', '50% Reduction'),
            ('95', '95% Reduction'),
        ],
        string="Reduction Level",
        default='0',
        help="Reduction level to assign to matching products. Only "
             "meaningful for excise types that have reduction "
             "support (Kemikalieskatt). Ignored for nicotine, "
             "tobacco, and other regimes.",
    )

    # ------------------------------------------------------------------
    # Lookup helper used by product.template's onchange and the
    # bulk-apply server action.
    # ------------------------------------------------------------------
    @api.model
    def _find_for_product(self, product):
        """Return the most specific active rule for ``product``,
        or an empty recordset.

        ``product`` may be a ``product.template`` or a
        ``product.product`` — both have ``categ_id``.

        Lookup order:
          1. Active rule with ``product_category_id`` matching the
             product's category, lowest sequence wins.
          2. Active rule with no ``product_category_id`` (the
             "all products" fallback), lowest sequence wins.
        """
        if not product:
            return self.browse()
        # 1. Category-specific match.
        category = product.categ_id
        rule = self.browse()
        if category:
            rule = self.search(
                [
                    ('active', '=', True),
                    ('product_category_id', '=', category.id),
                ],
                order='sequence, id',
                limit=1,
            )
        # 2. Fallback to "all products" rules.
        if not rule:
            rule = self.search(
                [
                    ('active', '=', True),
                    ('product_category_id', '=', False),
                ],
                order='sequence, id',
                limit=1,
            )
        return rule
