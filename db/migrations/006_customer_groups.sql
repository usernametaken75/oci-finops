-- 006_customer_groups.sql
-- Customer/team grouping table and materialized view for per-group cost dashboards.
-- Maps compartments to external customers (AMS, USA Rugby, Ford Meter Box) and
-- internal teams (AI, Ops, CNC, Oracle).

BEGIN;

-- Reference table mapping compartments to customer/team groups
CREATE TABLE IF NOT EXISTS customer_groups (
    compartment_name  TEXT PRIMARY KEY,
    group_name        TEXT NOT NULL,
    sub_team          TEXT,
    display_name      TEXT NOT NULL
);

-- Seed: External customers
INSERT INTO customer_groups (compartment_name, group_name, sub_team, display_name) VALUES
    ('AMS_JDE',                   'AMS',            NULL,     'AMS'),
    ('RUG_JDE22',                 'USA Rugby',      NULL,     'USA Rugby'),
    ('FMB-POC',                   'Ford Meter Box', NULL,     'Ford Meter Box')
ON CONFLICT (compartment_name) DO UPDATE
    SET group_name   = EXCLUDED.group_name,
        sub_team     = EXCLUDED.sub_team,
        display_name = EXCLUDED.display_name;

-- Seed: Internal - AI team
INSERT INTO customer_groups (compartment_name, group_name, sub_team, display_name) VALUES
    ('ERP-Analytics',             'Internal', 'AI',     'AI - ERP Analytics'),
    ('FDA-Demo',                  'Internal', 'AI',     'AI - FDA Demo'),
    ('INFOCUS-HOL',               'Internal', 'AI',     'AI - InFocus HOL'),
    ('AI-CMA-Sandbox',            'Internal', 'AI',     'AI - CMA Sandbox'),
    ('AI-POTOSO-Develop',         'Internal', 'AI',     'AI - POTOSO Develop'),
    ('ERP-Analytics-Development', 'Internal', 'AI',     'AI - ERP Analytics Dev'),
    ('AI-CMA-Demo',               'Internal', 'AI',     'AI - CMA Demo'),
    ('AI-POTOSO',                 'Internal', 'AI',     'AI - POTOSO')
ON CONFLICT (compartment_name) DO UPDATE
    SET group_name   = EXCLUDED.group_name,
        sub_team     = EXCLUDED.sub_team,
        display_name = EXCLUDED.display_name;

-- Seed: Internal - Ops team
INSERT INTO customer_groups (compartment_name, group_name, sub_team, display_name) VALUES
    ('Database',                  'Internal', 'Ops',    'Ops - Database'),
    ('ociLZPOC-security-cmp',     'Internal', 'Ops',    'Ops - Security'),
    ('erpsuitesoci',              'Internal', 'Ops',    'Ops - ERPSuites OCI')
ON CONFLICT (compartment_name) DO UPDATE
    SET group_name   = EXCLUDED.group_name,
        sub_team     = EXCLUDED.sub_team,
        display_name = EXCLUDED.display_name;

-- Seed: Internal - CNC team
INSERT INTO customer_groups (compartment_name, group_name, sub_team, display_name) VALUES
    ('Cristie_POC',               'Internal', 'CNC',    'CNC - Cristie POC'),
    ('erpsuites-jde-lab',         'Internal', 'CNC',    'CNC - JDE Lab')
ON CONFLICT (compartment_name) DO UPDATE
    SET group_name   = EXCLUDED.group_name,
        sub_team     = EXCLUDED.sub_team,
        display_name = EXCLUDED.display_name;

-- Seed: Internal - Oracle (AI Week)
INSERT INTO customer_groups (compartment_name, group_name, sub_team, display_name) VALUES
    ('askData-appdev-cmp',        'Internal', 'Oracle', 'Oracle - AppDev'),
    ('askData-database-cmp',      'Internal', 'Oracle', 'Oracle - Database'),
    ('askData-network-cmp',       'Internal', 'Oracle', 'Oracle - Network')
ON CONFLICT (compartment_name) DO UPDATE
    SET group_name   = EXCLUDED.group_name,
        sub_team     = EXCLUDED.sub_team,
        display_name = EXCLUDED.display_name;

-- Daily cost aggregation by customer/team group
CREATE MATERIALIZED VIEW IF NOT EXISTS mv_daily_cost_by_group AS
SELECT
    date_trunc('day', r.chargeperiodstart)::date    AS cost_date,
    COALESCE(g.group_name, 'Internal')              AS group_name,
    COALESCE(g.sub_team, 'Ops')                     AS sub_team,
    COALESCE(g.display_name, r.oci_compartmentname) AS display_name,
    r.oci_compartmentname                           AS compartment_name,
    r.servicename,
    r.servicecategory,
    SUM(r.billedcost)                               AS total_billed_cost,
    SUM(r.effectivecost)                            AS total_effective_cost,
    SUM(r.listcost)                                 AS total_list_cost,
    COUNT(*)                                        AS line_item_count
FROM oci_finops_reports r
LEFT JOIN customer_groups g ON r.oci_compartmentname = g.compartment_name
WHERE r.chargecategory = 'Usage'
GROUP BY 1, 2, 3, 4, 5, 6, 7
ORDER BY 1 DESC, 8 DESC;

CREATE UNIQUE INDEX IF NOT EXISTS idx_mv_daily_cost_group
    ON mv_daily_cost_by_group (cost_date, group_name, sub_team, compartment_name, servicename, servicecategory);

-- Update refresh function to include the new view
CREATE OR REPLACE FUNCTION refresh_finops_views()
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_service;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_compartment;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_monthly_cost_summary;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_cost_by_region;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_cost_by_group;
END;
$$;

COMMIT;
