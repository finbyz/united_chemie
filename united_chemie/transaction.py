import json
from collections import defaultdict

import frappe
from frappe import _, bold
from frappe.model import delete_doc
from frappe.utils import cint, flt
from erpnext.controllers.accounts_controller import get_taxes_and_charges

from india_compliance.gst_india.constants import (
    GST_TAX_TYPES,
    SALES_DOCTYPES,
    STATE_NUMBERS,
)
from india_compliance.gst_india.constants.custom_fields import E_WAYBILL_INV_FIELDS
from india_compliance.gst_india.overrides.transaction import ItemGSTDetails
from india_compliance.gst_india.utils import (
    get_all_gst_accounts,
    get_gst_accounts_by_tax_type,
    get_gst_accounts_by_type,
    get_hsn_settings,
    get_place_of_supply,
    get_place_of_supply_options,
    is_overseas_doc,
    join_list_with_custom_separators,
    validate_gst_category,
    validate_gstin,
)
from india_compliance.income_tax_india.overrides.tax_withholding_category import (
    get_tax_withholding_accounts,
)
from india_compliance.gst_india.overrides.transaction import (validate_place_of_supply, ignore_gst_validations, validate_company_address_field, validate_mandatory_fields, 
validate_overseas_gst_category,validate_gst_accounts,update_taxable_values,set_reverse_charge_as_per_gst_settings,validate_ecommerce_gstin,validate_hsn_codes,validate_gst_transporter_id, validate_reverse_charge_transaction, validate_gstin_status)

DOCTYPES_WITH_GST_DETAIL = {
    "Supplier Quotation",
    "Purchase Order",
    "Purchase Receipt",
    "Quotation",
    "Sales Order",
    "Delivery Note",
    "Sales Invoice",
    "POS Invoice",
}

def custom_validate_item_wise_tax_detail(doc, gst_accounts):
    if doc.doctype not in DOCTYPES_WITH_GST_DETAIL:
        return

    item_taxable_values = defaultdict(float)

    for row in doc.items:
        item_key = row.item_code or row.item_name
        item_taxable_values[item_key] += row.taxable_value

    for row in doc.taxes:
        if row.account_head not in gst_accounts:
            continue

        if row.charge_type != "Actual":
            continue

        item_wise_tax_detail = frappe.parse_json(row.item_wise_tax_detail or "{}")
        # FINBYZ CHANGES START WE HAVE OVERRIDED THIS FUNCTION FROM INDIA COMPLIANCE TO STOP THROW WHEN WE ADD ADD TAXES MANUALLY IN ACTUAL MODE
        for item_name, (tax_rate, tax_amount) in item_wise_tax_detail.items():
            if tax_amount and not tax_rate:
                pass
                # frappe.throw(
                #     _(
                #         "Tax Row #{0}: Charge Type is set to Actual. However, this would"
                #         " not compute item taxes, and your further reporting will be affected."
                #     ).format(row.idx),
                #     title=_("Invalid Charge Type"),
                # )

            # Sales Invoice is created with manual tax amount. So, when a sales return is created,
            # the tax amount is not recalculated, causing the issue.
            item_taxable_value = item_taxable_values.get(item_name, 0)
            tax_difference = abs(item_taxable_value * tax_rate / 100 - tax_amount)

            if tax_difference > 1:
                pass
                # frappe.throw(
                #     _(
                #         "Tax Row #{0}: Charge Type is set to Actual. However, Tax Amount {1} as computed for Item {2}"
                #         " is incorrect. Try setting the Charge Type to On Net Total."
                #     ).format(row.idx, tax_amount, bold(item_name))
                # )
        # FINBYZ CHANGES END    

def get_(self, docs, doctype, company):
    """
    Return Item GST Details for a list of documents
    """
    self.set_gst_accounts_and_item_defaults(doctype, company)
    self.set_tax_amount_precisions(doctype)

    response = frappe._dict()

    if not self.gst_account_map:
        return response

    for doc in docs:
        self.doc = doc
        if not doc.get("items") or not doc.get("taxes"):
            continue

        self.set_item_wise_tax_details()

        max_idx = 0
        if idxs := [item.idx for item in self.doc.get("items")]:
            max_idx = max(idxs)

        for item in doc.get("items"):
            response[item.name] = self.get_item_tax_detail(item, max_idx)

    return response

def set_item_wise_tax_details_(self):
    """
    Item Tax Details complied
    Example:
    {
        "Item Code 1": {
            "count": 2,
            "cgst_rate": 9,
            "cgst_amount": 18,
            "sgst_rate": 9,
            "sgst_amount": 18,
            ...
        },
        ...
    }

    Possible Exceptions Handled:
    - There could be more than one row for same account
    - Item count added to handle rounding errors
    """

    tax_details = frappe._dict()

    for row in self.doc.get("items"):
        key = row.item_code or row.item_name
        if key not in tax_details:
            tax_details[key] = self.item_defaults.copy()
        tax_details[key]["count"] += 1

    for row in self.doc.taxes:
        if (
            not row.tax_amount
            or not row.item_wise_tax_detail
            or row.account_head not in self.gst_account_map
        ):
            continue

        account_type = self.gst_account_map[row.account_head]
        tax = account_type[:-8]
        tax_rate_field = f"{tax}_rate"
        tax_amount_field = f"{tax}_amount"

        old = json.loads(row.item_wise_tax_detail)
        base_tax_amount = flt(row.base_tax_amount, 2)

        # update item taxes
        for idx, item_name in enumerate(old):
            if item_name not in tax_details:
                # Do not compute if Item is not present in Item table
                # There can be difference in Item Table and Item Wise Tax Details
                continue

            item_taxes = tax_details[item_name]
            tax_rate, tax_amount = old[item_name]

            tax_amount = flt(tax_amount, 2)
            base_tax_amount = flt(base_tax_amount - tax_amount, 2)

            # cases when charge type == "Actual"
            if tax_amount and not tax_rate:
                continue

            item_taxes[tax_rate_field] = tax_rate
            item_taxes[tax_amount_field] += tax_amount
        
        item_taxes[tax_amount_field] += base_tax_amount

    self.item_tax_details = tax_details

def get_item_tax_detail_(self, item, max_idx=0):
    """
    - get item_tax_detail as it is if
        - only one row exists for same item
        - it is the last item

    - If count is greater than 1,
        - Manually calculate tax_amount for item
        - Reduce item_tax_detail with
            - tax_amount
            - count
    """
    item_key = self.get_item_key(item)

    item_tax_detail = self.item_tax_details.get(item_key)
    if not item_tax_detail:
        return {}

    #FINBYZ CHAGE START TO MAINTAIN PRECISION IN SALES INVOICE TAX CALCULATION: COMMENTED BELOW LINE

    # if item_tax_detail.count == 1:
    #     return item_tax_detail

    #FINBYZ CHAGES END TO MAINTAIN PRECISION IN SALES INVOICE TAX CALCULATION

    item_tax_detail["count"] -= 1

    # Handle rounding errors
    response = item_tax_detail.copy()
    for tax in GST_TAX_TYPES:
        if (tax_rate := item_tax_detail[f"{tax}_rate"]) == 0:
            continue

        tax_amount_field = f"{tax}_amount"
        precision = self.precision.get(tax_amount_field)

        multiplier = (
            item.qty if tax == "cess_non_advol" else item.taxable_value / 100
        )
        tax_amount = flt(tax_rate * multiplier, precision)

        if item.idx == max_idx:
            tax_amount = item_tax_detail[tax_amount_field]

        item_tax_detail[tax_amount_field] -= tax_amount

        response.update({tax_amount_field: tax_amount})

    return response

def update_item_tax_details_(self):
    max_idx = 0
    if idxs := [item.idx for item in self.doc.get("items")]:
        max_idx = max(idxs)
    
    for item in self.doc.get("items"):
        item.update(self.get_item_tax_detail(item, max_idx))
