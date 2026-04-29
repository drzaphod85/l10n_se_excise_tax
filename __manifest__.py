# -*- coding: utf-8 -*-
{
    'name': 'Swedish Excise Tax (Chemical Tax)',
    'version': '19.0.3.3.3',
    'category': 'Accounting/Localizations',
    'summary': 'Manage chemical taxes and other excise duties applied before VAT.',
    'description': """
Swedish Excise Tax Management
=============================
This module allows for the calculation of specific excise taxes (like the Swedish Chemical Tax) 
based on product weight and unit caps. 

Key features:
* Define excise tax types with custom rates and maximum limits.
* Apply reductions (e.g., 50% or 90%) per product.
* Calculation logic integrated with Odoo's tax engine.
* Support for taxes being included in the VAT base.
    """,
    'author': 'Lasse Larsson',
    'depends': ['account', 'product', 'sale', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'data/excise_tax_data.xml',
        'views/product_views.xml',
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