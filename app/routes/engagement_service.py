
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from app.models import db, VatFilingMonth, VatMonthlySummary, Job, InstallmentTaxSummary, TaxLiabilitySummary

def update_historical_summaries(job_id: int, form_data: dict):
    """
    Parses form data to find and update historical VAT monthly summaries.
    """
    
    historical_updates = defaultdict(dict)
    editable_summary_fields = [
        'sales_zero_rated', 'sales_exempt', 'sales_vatable_16', 'sales_vatable_8',
        'output_vat_16', 'output_vat_8', 'purchases_zero_rated', 'purchases_exempt',
        'purchases_vatable_16', 'purchases_vatable_8', 'input_vat_16', 'input_vat_8',
        'withheld_vat', 'balance_bf', 'paid'
    ]
    
    for key, value in form_data.items():
        parts = key.rsplit('_', 1)
        if len(parts) == 2:
            field_name, month_key = parts
            if field_name in editable_summary_fields:
                try:
                    decimal_value = Decimal(value) if value and value.strip() else None
                    historical_updates[month_key.upper()][field_name] = decimal_value
                except (ValueError, TypeError, InvalidOperation):
                    pass
    
    if not historical_updates:
        return

    # Get ALL summary objects for the job from the DB.
    all_job_summaries = VatMonthlySummary.query.filter_by(job_id=job_id).all()
    
    # Create a smart map using the SHORT month name as the key.
    summaries_map = {s.month[:3].upper(): s for s in all_job_summaries}

    # Loop through the form data and update the correct objects from our map.
    updated_count = 0
    for month_key, fields in historical_updates.items():
        summary_object = summaries_map.get(month_key)
        if summary_object:
            for field_name, new_value in fields.items():
                old_value = getattr(summary_object, field_name)
                setattr(summary_object, field_name, new_value)
                updated_count += 1
        else:
            # Create new summary if it doesn't exist
            new_summary = VatMonthlySummary(
                job_id=job_id,
                month=month_key,
                **fields
            )
            db.session.add(new_summary)
            updated_count += 1
    
    return {
        'updated_or_created': updated_count
    }


def update_current_month_vat_data(vat_form: VatFilingMonth, summary: VatMonthlySummary, form_data: dict):
    """
    Updates the main VatFilingMonth form and its corresponding summary object.

    This function takes the raw data from the main form, updates the detailed
    VatFilingMonth object, and then uses its calculated properties to update
    the single VatMonthlySummary object for the current period.

    Args:
        vat_form: The VatFilingMonth SQLAlchemy object for the current month.
        summary: The VatMonthlySummary SQLAlchemy object for the current month.
        form_data: The full request data dictionary.

    Returns:
        The updated VatMonthlySummary object.
    
    NOTE: This function does NOT commit the session.
    """
    # Helper functions to safely convert data types
    def to_decimal(value):
        if value is None or str(value).strip() == '': return None
        try: return Decimal(str(value))
        except: return None
    
    def to_int(value):
        if value is None or str(value).strip() == '': return None
        try: return int(value)
        except: return None

    # 1. Update the detailed VatFilingMonth object with raw inputs from the form
    vat_form.reg_customers_vatable_16 = to_decimal(form_data.get('reg_customers_vatable_16'))
    vat_form.reg_customers_vatable_8 = to_decimal(form_data.get('reg_customers_vatable_8'))
    vat_form.reg_customers_zero_rated = to_decimal(form_data.get('reg_customers_zero_rated'))
    vat_form.reg_customers_exempt = to_decimal(form_data.get('reg_customers_exempt'))

    vat_form.non_reg_customers_vatable_16 = to_decimal(form_data.get('non_reg_customers_vatable_16'))
    vat_form.non_reg_customers_vatable_8 = to_decimal(form_data.get('non_reg_customers_vatable_8'))
    vat_form.non_reg_customers_zero_rated = to_decimal(form_data.get('non_reg_customers_zero_rated'))
    vat_form.non_reg_customers_exempt = to_decimal(form_data.get('non_reg_customers_exempt'))

    vat_form.purchases_vatable_16 = to_decimal(form_data.get('purchases_vatable_16'))
    vat_form.purchases_vatable_8 = to_decimal(form_data.get('purchases_vatable_8'))
    vat_form.purchases_zero_rated = to_decimal(form_data.get('purchases_zero_rated'))
    vat_form.purchases_exempt = to_decimal(form_data.get('purchases_exempt'))
    
    vat_form.vat_wh_credit = to_decimal(form_data.get('vat_wh_credit'))
    vat_form.credit_bf = to_decimal(form_data.get('credit_bf'))
    vat_form.vat_payable_override = to_decimal(form_data.get('vat_payable_override'))
    
    vat_form.paye_employees = to_int(form_data.get('paye_employees'))
    vat_form.paye_amount = to_decimal(form_data.get('paye_amount'))
    vat_form.shif_employees = to_int(form_data.get('shif_employees'))
    vat_form.shif = to_decimal(form_data.get('shif'))
    vat_form.nssf_employees = to_int(form_data.get('nssf_employees'))
    vat_form.nssf = to_decimal(form_data.get('nssf'))

    # 2. Now, use the calculated properties from the updated vat_form to populate the summary
    summary.sales_zero_rated = vat_form.total_sales_zero_rated
    summary.sales_exempt = vat_form.total_sales_exempt
    summary.sales_vatable_16 = (vat_form.reg_customers_vatable_16 or 0) + (vat_form.non_reg_customers_vatable_16 or 0)
    summary.sales_vatable_8 = (vat_form.reg_customers_vatable_8 or 0) + (vat_form.non_reg_customers_vatable_8 or 0)
    
    summary.output_vat_16 = summary.sales_vatable_16 * Decimal('0.16')
    summary.output_vat_8 = summary.sales_vatable_8 * Decimal('0.08')

    summary.purchases_zero_rated = vat_form.purchases_zero_rated
    summary.purchases_exempt = vat_form.purchases_exempt
    summary.purchases_vatable_16 = vat_form.purchases_vatable_16
    summary.purchases_vatable_8 = vat_form.purchases_vatable_8

    summary.input_vat_16 = (summary.purchases_vatable_16 or 0) * Decimal('0.16')
    summary.input_vat_8 = (summary.purchases_vatable_8 or 0) * Decimal('0.08')

    summary.withheld_vat = vat_form.vat_wh_credit
    summary.balance_bf = vat_form.credit_bf
    # The 'paid' value for the current summary comes from the historical table inputs
    summary.paid = to_decimal(form_data.get(f'paid_{summary.month}', 0))

    return summary

def update_banking_and_salary(job: Job, form_data: dict):
    """Parses form data to update Banking and Gross Salary summaries."""
    banking_map = {s.month: s for s in job.banking_summaries}
    salary_map = {s.month: s for s in job.salary_summaries}

    for key, value in form_data.items():
        # Safely convert to Decimal
        try:
            decimal_value = Decimal(value) if value else None
        except InvalidOperation:
            continue # Skip non-numeric values

        if key.startswith('bc_total_credits_'):
            month_abbr = key.replace('bc_total_credits_', '')
            if banking_map.get(month_abbr):
                banking_map[month_abbr].total_credits = decimal_value
        
        elif key.startswith('gs_gross_salary_'):
            month_abbr = key.replace('gs_gross_salary_', '')
            if salary_map.get(month_abbr):
                salary_map[month_abbr].gross_salary = decimal_value

def update_installment_tax(job: Job, form_data: dict):
    """Updates the single InstallmentTaxSummary object for the job."""
    summary = job.installment_tax_summary
    if not summary:
        summary = InstallmentTaxSummary(job_id=job.id)
        db.session.add(summary)

    def to_decimal(key):
        val = form_data.get(key)
        try: return Decimal(val) if val else None
        except (InvalidOperation, TypeError): return None

    summary.installment_tax_1 = to_decimal('installment_tax_1')
    summary.installment_tax_2 = to_decimal('installment_tax_2')
    summary.installment_tax_3 = to_decimal('installment_tax_3')
    summary.installment_tax_4 = to_decimal('installment_tax_4')

    # Handle boolean conversion from form strings
    summary.installment_paid_1 = form_data.get('installment_paid_1') == 'true'
    summary.installment_paid_2 = form_data.get('installment_paid_2') == 'true'
    summary.installment_paid_3 = form_data.get('installment_paid_3') == 'true'
    summary.installment_paid_4 = form_data.get('installment_paid_4') == 'true'

def update_tax_liabilities(job: Job, form_data: dict):
    """Updates existing, creates new, and deletes Tax Liability records."""
    liability_map = {str(l.id): l for l in job.tax_liabilities}
    updates_by_id = defaultdict(dict)
    liabilities_to_delete = set()

    def to_decimal(val):
        try: 
            return Decimal(val) if val else None
        except (InvalidOperation, TypeError): 
            return None

    # 1. First, identify which records should be deleted
    for key, value in form_data.items():
        if key.startswith('tl_delete_'):
            liability_id = key.replace('tl_delete_', '')
            
            # Check the actual value
            should_delete = False
            
            if isinstance(value, bool):
                should_delete = value
            elif isinstance(value, str):
                should_delete = value.lower() in ['true', 'on', '1', 'yes']
            elif value == 1 or value == "1":
                should_delete = True
                
            if should_delete:
                liabilities_to_delete.add(liability_id)
    
    # 2. Group updates for existing liabilities (excluding those marked for deletion)
    for key, value in form_data.items():
        if key.startswith('tl_') and not key.startswith('tl_delete_'):
            parts = key.split('_')  # e.g., ['tl', 'principal', '5']
            if len(parts) == 3:
                field, liability_id = parts[1], parts[2]
                if liability_id not in liabilities_to_delete:
                    updates_by_id[liability_id][field] = value

    # 3. Delete marked liabilities
    deleted_count = 0
    for liability_id in liabilities_to_delete:
        liability = liability_map.get(liability_id)
        if liability:
            db.session.delete(liability)
            deleted_count += 1
            updates_by_id.pop(liability_id, None)

    # 4. Apply updates to remaining liabilities
    updated_count = 0
    for liability_id, fields in updates_by_id.items():
        liability = liability_map.get(liability_id)
        if liability and liability_id not in liabilities_to_delete:
            liability.period = fields.get('period', liability.period)
            liability.tax_head = fields.get('tax_head', liability.tax_head)
            liability.principal = to_decimal(fields.get('principal'))
            liability.penalty = to_decimal(fields.get('penalty'))
            liability.interest = to_decimal(fields.get('interest'))
            liability.total = to_decimal(fields.get('total'))
            updated_count += 1

    # 5. Handle creation of new liabilities from array inputs
    # For single new entry (original format)
    new_period = form_data.get('new_tl_period')
    if new_period and new_period.strip():
        new_liability = TaxLiabilitySummary(
            job_id=job.id,
            period=new_period,
            tax_head=form_data.get('new_tl_tax_head'),
            principal=to_decimal(form_data.get('new_tl_principal')),
            penalty=to_decimal(form_data.get('new_tl_penalty')),
            interest=to_decimal(form_data.get('new_tl_interest')),
            total=to_decimal(form_data.get('new_tl_total'))
        )
        db.session.add(new_liability)
    
    # For multiple new entries from dynamic rows (array format)
    new_periods = form_data.get('new_tl_period[]')
    new_tax_heads = form_data.get('new_tl_tax_head[]')
    new_principals = form_data.get('new_tl_principal[]')
    new_penalties = form_data.get('new_tl_penalty[]')
    new_interests = form_data.get('new_tl_interest[]')
    new_totals = form_data.get('new_tl_total[]')
    
    # Check if we have array inputs
    if isinstance(new_periods, list):
        created_count = 0
        for i in range(len(new_periods)):
            period = new_periods[i]
            if period and period.strip():
                liability = TaxLiabilitySummary(
                    job_id=job.id,
                    period=period,
                    tax_head=new_tax_heads[i] if i < len(new_tax_heads) else None,
                    principal=to_decimal(new_principals[i] if i < len(new_principals) else None),
                    penalty=to_decimal(new_penalties[i] if i < len(new_penalties) else None),
                    interest=to_decimal(new_interests[i] if i < len(new_interests) else None),
                    total=to_decimal(new_totals[i] if i < len(new_totals) else None)
                )
                db.session.add(liability)
                created_count += 1
    
    elif new_periods and isinstance(new_periods, str) and new_periods.strip():
        # Handle single value that might come as array
        liability = TaxLiabilitySummary(
            job_id=job.id,
            period=new_periods,
            tax_head=form_data.get('new_tl_tax_head[]'),
            principal=to_decimal(form_data.get('new_tl_principal[]')),
            penalty=to_decimal(form_data.get('new_tl_penalty[]')),
            interest=to_decimal(form_data.get('new_tl_interest[]')),
            total=to_decimal(form_data.get('new_tl_total[]'))
        )
        db.session.add(liability)
    
    return {
        'deleted': deleted_count,
        'updated': updated_count,
        'marked_for_deletion': list(liabilities_to_delete)
    }
