import pandas as pd
import re
import json
import os
from pathlib import Path
from tabulate import tabulate
import yaml
import matplotlib.pyplot as plt


def plot_papers_per_category_year(df, category_col, output_path):
    """
    Plot stacked bar chart of papers per category (e.g., TRL or AI) per year.
    """
    # Ensure Year is numeric (drop non-numeric like "NA")
    df = df.copy()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")

    # Drop rows without valid Year
    df = df.dropna(subset=["Year"])
    df["Year"] = df["Year"].astype(int)

    # Ensure category column is categorical
    if df[category_col].dtype != "category":
        df[category_col] = df[category_col].astype("category")

    # Count papers per category per year
    counts = (
        df.groupby(["Year", category_col], observed=False)
        .size()
        .reset_index(name="count")
    )

    # Pivot for plotting
    pivot_df = counts.pivot(index="Year", columns=category_col, values="count").fillna(
        0
    )

    # Plot
    pivot_df.plot(kind="bar", stacked=True, figsize=(10, 6))
    plt.title(f"Number of papers per year classified by {category_col}")
    plt.ylabel("Number of Papers")
    plt.xlabel("Year")
    plt.legend(title=category_col, loc="upper left")
    plt.grid(axis="y", linestyle="--", alpha=0.7)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)


# Load the issue body from environment variable (preferred) or file
body = os.environ.get("ISSUE_BODY", "")
if not body:
    with open("issue_body.txt", "r", encoding="utf-8") as f:
        body = f.read()


def extract_field(field_label):
    pattern = rf"(?:^|\n)###\s+{re.escape(field_label)}\s*\n\n([^\n]+)"
    match = re.search(pattern, body)
    if match:
        value = match.group(1).strip().strip("_")
        if value.lower() == "no response":
            return ""
        return value
    return ""


# --- Load config files ---
domains_path = Path("./config/domains.json")
fault_injections_path = Path("./config/fault_injections.json")

domains = json.loads(domains_path.read_text())
fault_injections = json.loads(fault_injections_path.read_text())

# --- Extract fields from issue ---
domain_selected = extract_field("Domain")
domain_other = extract_field("If Domain is 'Other', please specify below")
fault_injection_other = extract_field(
    "If Fault Injection is 'Other', please specify below new fault Injection types separated by commas (new ID will be automatically generated)"
)
raw_threats = extract_field("Targeted Threats")
threats_list = [t.strip() for t in re.split(r"[,\n]", raw_threats) if t.strip()]
threats_codes = [re.match(r"^\w", t).group(0) for t in threats_list]
targeted_threats_str = ", ".join(threats_codes)

# --- Process Fault Injections ---
raw_fi = extract_field("Fault Injection")
fi_list = [t.strip() for t in re.split(r"[,\n]", raw_fi) if t.strip()]

# Extract just the Tx codes (like T1, T2, ...) for selected options
fi_codes = []
for fi in fi_list:
    match = re.match(r"^(T\d+)", fi)
    if match:
        fi_codes.append(match.group(1))

# Handle 'Other' entries
if fault_injection_other:
    # Split by comma if user added multiple new types
    new_fis = [t.strip() for t in fault_injection_other.split(",") if t.strip()]
    # Determine the next Tx number
    existing_numbers = [
        int(re.match(r"T(\d+)", x).group(1))
        for x in fault_injections
        if re.match(r"T\d+", x)
    ]
    next_number = max(existing_numbers, default=0) + 1

    for new_fi in new_fis:
        new_tx = f"T{next_number} ({new_fi})"
        if new_tx not in fault_injections:
            fault_injections.append(new_tx)
            next_number += 1
        fi_codes.append(re.match(r"(T\d+)", new_tx).group(1))

    # Save updated JSON
    fault_injections_path.write_text(json.dumps(fault_injections, indent=2))

# Combine selected Tx codes as comma-separated string
fault_injections_str = ", ".join(fi_codes)


# --- Update JSON lists if 'Other' is specified ---
if domain_other:
    if domain_other not in domains:
        domains.append(domain_other)
        domains_path.write_text(json.dumps(domains, indent=2))
    domain_selected = domain_other

# Extract year and enforce integer
year_str = extract_field("Year").strip()
if not year_str:
    raise ValueError("Year field is required but missing.")

try:
    year_val = int(year_str)
except ValueError:
    raise ValueError(f"Invalid Year value: {year_str}. Must be an integer.")

entry = {
    "DOI": extract_field("DOI"),
    "Year": year_val,
    "Domain": domain_selected,
    "TRL": extract_field("TRL"),
    "AI": extract_field("AI-based"),
    "Targeted Threats": targeted_threats_str,
    "Attack Scenarios": extract_field("Attack Scenarios"),
    "Fault Injection": fault_injections_str,
    "Evaluation Method": extract_field("Evaluation Method"),
    # --- optional free-text fields ---
    "Identified Security Challenges": extract_field("Identified Security Challenges"),
    "Contributions": extract_field("Contributions"),
    "Use Case Description": extract_field("Use Case Description"),
    "Prerequisites": extract_field("Prerequisites"),
    "SCE Approach Description": extract_field("SCE Approach Description"),
    "Required Resources": extract_field("Required Resources"),
    "Evaluation Approach Description": extract_field("Evaluation Approach Description"),
    "Evaluation Metrics": extract_field("Evaluation Metrics"),
    "Evaluation Results": extract_field("Evaluation Results"),
    "Lessons Learned": extract_field("Lessons Learned"),
    "Additional Information": extract_field("Additional Information"),
}

# --- Debug print ---
print("\n--- EXTRACTED VALUES ---")
for k, v in entry.items():
    print(f"{k}: {v}")
print("------------------------\n")

# --- Append to CSV ---
df = pd.read_csv("slr.csv")
df.columns = df.columns.str.strip()
df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
required_fields = [
    "DOI",
    "Year",
    "Domain",
    "TRL",
    "AI",
    "Targeted Threats",
    "Attack Scenarios",
    "Fault Injection",
    "Evaluation Method",
]
df[required_fields] = df[required_fields].fillna("NA")
df.to_csv("slr.csv", index=False)

# --- Debug print of updated CSV ---
print("\n--- UPDATED CSV CONTENT ---")
print(tabulate(df, headers="keys", tablefmt="pretty", showindex=False))
print("--------------------------------\n")

plot_papers_per_category_year(df, "AI", "papers_with_ai_per_year.png")

# --- Update issue form ---
if domain_other or fault_injection_other:
    domains.extend(["Other (please specify below)", "NA"])
    fault_injections.extend(["Other (please specify below)", "NA"])

    # Define YAML template
    form = {
        "name": "Add SLR Entry",
        "description": "Submit a new study for inclusion in the SLR",
        "title": "[SLR Entry] ",
        "labels": ["slr-entry"],
        "body": [
            {
                "type": "input",
                "id": "doi",
                "attributes": {"label": "DOI", "placeholder": "10.5281/zenodo.XXXXXXX"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "year",
                "attributes": {
                    "label": "Year",
                    "placeholder": "YYYY",
                    "description": "Enter the 4-digit publication year (e.g., 2025)",
                },
                "validations": {"required": True},
            },
            {
                "type": "dropdown",
                "id": "domain",
                "attributes": {"label": "Domain", "multiple": True, "options": domains},
                "validations": {"required": True},
            },
            {
                "type": "input",
                "id": "domain_other_specify",
                "attributes": {
                    "label": "If Domain is 'Other', please specify below",
                    "description": "Leave blank if not applicable",
                },
                "validations": {"required": False},
            },
            {
                "type": "dropdown",
                "id": "trl",
                "attributes": {"label": "TRL", "options": ["1-3", "4-6", "7-9", "NA"]},
                "validations": {"required": True},
            },
            {
                "type": "dropdown",
                "id": "ai",
                "attributes": {"label": "AI-based", "options": ["Yes", "No"]},
                "validations": {"required": True},
            },
            {
                "type": "dropdown",
                "id": "targeted_threats",
                "attributes": {
                    "label": "Targeted Threats",
                    "multiple": True,
                    "options": [
                        "S (Spoofing)",
                        "T (Tampering)",
                        "R (Repudiation)",
                        "I (Information Disclosure)",
                        "D (Denial of Service)",
                        "E (Elevation of Privilege)",
                        "NA",
                    ],
                },
                "validations": {"required": True},
            },
            {
                "type": "input",
                "id": "attack_scenarios",
                "attributes": {
                    "label": "Attack Scenarios",
                    "description": "Leave blank if not applicable",
                },
                "validations": {"required": False},
            },
            {
                "type": "dropdown",
                "id": "fault_injections",
                "attributes": {
                    "label": "Fault Injection",
                    "multiple": True,
                    "options": fault_injections,
                },
                "validations": {"required": True},
            },
            {
                "type": "input",
                "id": "fault_injection_other_specify",
                "attributes": {
                    "label": "If Fault Injection is 'Other', please specify below new fault Injection types separated by commas (new ID will be automatically generated)",
                    "description": "Leave blank if not applicable",
                },
                "validations": {"required": False},
            },
            {
                "type": "dropdown",
                "id": "evaluation_method",
                "attributes": {
                    "label": "Evaluation Method",
                    "multiple": True,
                    "options": ["Empirical", "Analytical", "NA"],
                },
                "validations": {"required": True},
            },
            # --- optional free text fields ---
            {
                "type": "markdown",
                "attributes": {
                    "value": "---\n## 📝 Optional Information\n*(Fill in if applicable, otherwise leave blank)*"
                },
            },
            {
                "type": "input",
                "id": "security_challenges",
                "attributes": {"label": "Identified Security Challenges"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "contributions",
                "attributes": {"label": "Contributions"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "use_case_description",
                "attributes": {"label": "Use Case Description"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "prerequisites",
                "attributes": {"label": "Prerequisites"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "sce_approach",
                "attributes": {"label": "SCE Approach Description"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "required_resources",
                "attributes": {"label": "Required Resources"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "evaluation_approach_description",
                "attributes": {"label": "Evaluation Approach Description"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "evaluation_metrics",
                "attributes": {"label": "Evaluation Metrics"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "evaluation_results",
                "attributes": {"label": "Evaluation Results"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "lessons_learned",
                "attributes": {"label": "Lessons Learned"},
                "validations": {"required": False},
            },
            {
                "type": "input",
                "id": "additional_info",
                "attributes": {"label": "Additional Information"},
                "validations": {"required": False},
            },
        ],
    }

    # Save YAML into .github/ISSUE_TEMPLATE/
    output_path = Path(".github/ISSUE_TEMPLATE/add_slr_entry.yml")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        yaml.dump(form, f, sort_keys=False)

    print(f"Issue form generated: {output_path}")
