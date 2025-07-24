import frappe

def validate(self,method):
    if self.stock_entry_type == "Manufacture" and self.work_order:
        for row in self.additional_costs:
            if row.expense_account:
                row.expense_account= row.description