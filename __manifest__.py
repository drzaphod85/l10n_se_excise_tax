# -*- coding: utf-8 -*-
{
    'name': 'Swedish Excise Tax (Chemical Tax)',
    'version': '19.0.5.0.0',
    'category': 'Accounting/Localizations',
    'summary': 'Manage chemical taxes and other excise duties applied before VAT.',
    'description': """
Swedish Excise Tax Management
=============================

This module allows for the calculation of specific excise taxes (like the
Swedish Chemical Tax) based on product weight, volume or piece count, with
optional per-unit caps.

Key features:

* Define excise tax types with custom rates and maximum limits (kg / liter / pcs basis).
* Apply Kemikalieskatt reductions per product (50% or 95% per Lag (2016:1067)).
* Default-rule engine: pick a default excise tax + reduction per product category, or a fallback for all products, so new products inherit the right configuration.
* Bulk "Apply Excise Defaults" server action to retro-apply rules to existing products.
* Calculation logic integrated with Odoo's tax engine.
* Support for taxes being included in the VAT base.
    """,
    'author': 'Lasse Larsson',
    'depends': ['account', 'product', 'sale', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/excise_tax_data.xml',
        'views/product_views.xml',
        'views/excise_tax_default_views.xml',
        'views/account_tax_views.xml',
        'views/account_move_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
        'views/report_templates.xml',
        'views/website_sale_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}