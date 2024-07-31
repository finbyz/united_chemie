import frappe
def before_save(self,method):
    calculate_inr_freight(self)

def calculate_inr_freight(self):
    for row in self.items:
        if row.freight:
            row.base_freight = row.freight * self.conversion_rate
            row.base_insurance = row.insurance * self.conversion_rate
            row.base_fob_value = row.fob_value / self.conversion_rate
    self.base_freight = self.freight * self.conversion_rate
    self.base_insurance = self.insurance * self.conversion_rate
    self.base_fob_value = self.total_fob_value / self.conversion_rate