"""One-time/rerunnable dev tool: live-validate seed-company candidates.

Takes a hardcoded candidate list (existing seed companies re-tagged with an
industry, plus newly researched candidates), hits the real Greenhouse/Ashby
job-board endpoints for each, and keeps only entries that return HTTP 200
with a non-empty job list. Survivors are written to
``lewis_api/agent/sources/seed_companies.yaml``.

Not part of the shipped ``lewis_api`` package and not covered by the
mocked-API test constraint -- it exists specifically to make real network
calls. Re-run it any time to refresh the seed list.

Usage:
    cd apps/api && uv run python scripts/validate_seed_companies.py
"""

from __future__ import annotations

import asyncio
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

_GREENHOUSE_URL = "https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
_ASHBY_URL = "https://api.ashbyhq.com/posting-api/job-board/{token}"

_OUTPUT_PATH = (
    Path(__file__).parent.parent
    / "lewis_api"
    / "agent"
    / "sources"
    / "seed_companies.yaml"
)

_HEADER = """\
# Seed list of companies to scan for jobs.
# Each entry: {company, source, board_token, industry} where source is
# "greenhouse" or "ashby", and industry is one of the taxonomy values used by
# lewis_api.agent.sources.seed.SeedEntry (see select_results.py diversity cap).
# All tokens below were live-verified (HTTP 200 + non-empty job list) via
# scripts/validate_seed_companies.py against:
#   greenhouse: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
#   ashby:      https://api.ashbyhq.com/posting-api/job-board/{board_token}
"""


@dataclass(frozen=True)
class Candidate:
    company: str
    board_token: str
    industry: str
    # "greenhouse", "ashby", or "auto" (try greenhouse, then ashby).
    source: str = "auto"


# ---------------------------------------------------------------------------
# Existing 106 seed companies, retagged with an industry (source already
# known precisely from the current seed_companies.yaml).
# ---------------------------------------------------------------------------
EXISTING: list[Candidate] = [
    Candidate("GitLab", "gitlab", "devtools", "greenhouse"),
    Candidate("Ramp", "ramp", "fintech", "ashby"),
    Candidate("Abnormal Security", "abnormalsecurity", "cybersecurity", "greenhouse"),
    Candidate("Affirm", "affirm", "fintech", "greenhouse"),
    Candidate("Airbnb", "airbnb", "consumer", "greenhouse"),
    Candidate("Airtable", "airtable", "enterprise_saas", "greenhouse"),
    Candidate("Alloy", "alloy", "fintech", "greenhouse"),
    Candidate("Amplitude", "amplitude", "enterprise_saas", "greenhouse"),
    Candidate("Anthropic", "anthropic", "ai_ml", "greenhouse"),
    Candidate("Asana", "asana", "enterprise_saas", "greenhouse"),
    Candidate("Attentive", "attentive", "enterprise_saas", "greenhouse"),
    Candidate("Benchling", "benchling", "biotech", "ashby"),
    Candidate("Betterment", "betterment", "fintech", "greenhouse"),
    Candidate("Blend", "blend", "fintech", "greenhouse"),
    Candidate("Branch", "branchmetrics", "devtools", "greenhouse"),
    Candidate("Braze", "braze", "enterprise_saas", "greenhouse"),
    Candidate("Brex", "brex", "fintech", "greenhouse"),
    Candidate("Brightwheel", "brightwheel", "edtech", "ashby"),
    Candidate("Carta", "carta", "fintech", "greenhouse"),
    Candidate("Checkr", "checkr", "enterprise_saas", "greenhouse"),
    Candidate("Chime", "chime", "fintech", "greenhouse"),
    Candidate("CircleCI", "circleci", "devtools", "greenhouse"),
    Candidate("ClassPass", "classpass", "consumer", "greenhouse"),
    Candidate("Clever", "clever", "edtech", "greenhouse"),
    Candidate("ClickHouse", "clickhouse", "devtools", "greenhouse"),
    Candidate("Cloudflare", "cloudflare", "cybersecurity", "greenhouse"),
    Candidate("Cockroach Labs", "cockroachlabs", "devtools", "greenhouse"),
    Candidate("Coinbase", "coinbase", "fintech", "greenhouse"),
    Candidate("Collective Health", "collectivehealth", "healthtech", "greenhouse"),
    Candidate("Column", "column", "fintech", "ashby"),
    Candidate("Coursera", "coursera", "edtech", "greenhouse"),
    Candidate("Cribl", "cribl", "devtools", "greenhouse"),
    Candidate("Current", "current", "fintech", "greenhouse"),
    Candidate("Databricks", "databricks", "ai_ml", "greenhouse"),
    Candidate("Datadog", "datadog", "devtools", "greenhouse"),
    Candidate("Diligent", "diligent", "enterprise_saas", "greenhouse"),
    Candidate("Discord", "discord", "consumer", "greenhouse"),
    Candidate("Dropbox", "dropbox", "enterprise_saas", "greenhouse"),
    Candidate("Elastic", "elastic", "devtools", "greenhouse"),
    Candidate("Faire", "faire", "ecommerce", "greenhouse"),
    Candidate("Figma", "figma", "enterprise_saas", "greenhouse"),
    Candidate("Fivetran", "fivetran", "devtools", "greenhouse"),
    Candidate("Flatiron Health", "flatironhealth", "healthtech", "greenhouse"),
    Candidate("Flexport", "flexport", "logistics_supply_chain", "greenhouse"),
    Candidate("Gemini", "gemini", "fintech", "greenhouse"),
    Candidate("Glossier", "glossier", "ecommerce", "greenhouse"),
    Candidate("Gusto", "gusto", "fintech", "greenhouse"),
    Candidate("HackerRank", "hackerrank", "enterprise_saas", "greenhouse"),
    Candidate("Handshake", "handshake", "edtech", "ashby"),
    Candidate("Harry's", "harrys", "ecommerce", "greenhouse"),
    Candidate("Hex", "hex", "devtools", "ashby"),
    Candidate("Instabase", "instabase", "ai_ml", "greenhouse"),
    Candidate("Instacart", "instacart", "ecommerce", "greenhouse"),
    Candidate("Intercom", "intercom", "enterprise_saas", "greenhouse"),
    Candidate("Justworks", "justworks", "enterprise_saas", "greenhouse"),
    Candidate("LaunchDarkly", "launchdarkly", "devtools", "greenhouse"),
    Candidate("Lattice", "lattice", "enterprise_saas", "greenhouse"),
    Candidate("Linear", "linear", "devtools", "ashby"),
    Candidate("Lyft", "lyft", "consumer", "greenhouse"),
    Candidate("Marqeta", "marqeta", "fintech", "greenhouse"),
    Candidate("Material Security", "materialsecurity", "cybersecurity", "ashby"),
    Candidate("Mercor", "mercor", "ai_ml", "ashby"),
    Candidate("Mixpanel", "mixpanel", "enterprise_saas", "greenhouse"),
    Candidate("Modern Treasury", "moderntreasury", "fintech", "ashby"),
    Candidate("MongoDB", "mongodb", "devtools", "greenhouse"),
    Candidate("Narvar", "narvar", "logistics_supply_chain", "greenhouse"),
    Candidate("Neo4j", "neo4j", "devtools", "greenhouse"),
    Candidate("New Relic", "newrelic", "devtools", "greenhouse"),
    Candidate("Newsela", "newsela", "edtech", "greenhouse"),
    Candidate("Nextdoor", "nextdoor", "consumer", "greenhouse"),
    Candidate("Notion", "notion", "enterprise_saas", "ashby"),
    Candidate("OpenAI", "openai", "ai_ml", "ashby"),
    Candidate("Okta", "okta", "cybersecurity", "greenhouse"),
    Candidate("Oscar Health", "oscar", "healthtech", "greenhouse"),
    Candidate("PagerDuty", "pagerduty", "devtools", "greenhouse"),
    Candidate("Peloton", "peloton", "consumer", "greenhouse"),
    Candidate("Perplexity", "perplexity", "ai_ml", "ashby"),
    Candidate("Persona", "persona", "cybersecurity", "ashby"),
    Candidate("Pinterest", "pinterest", "consumer", "greenhouse"),
    Candidate("PlanetScale", "planetscale", "devtools", "greenhouse"),
    Candidate("Postman", "postman", "devtools", "greenhouse"),
    Candidate("Reddit", "reddit", "consumer", "greenhouse"),
    Candidate("Replit", "replit", "devtools", "ashby"),
    Candidate("Rho", "rho", "fintech", "ashby"),
    Candidate("Ripple", "ripple", "fintech", "greenhouse"),
    Candidate("Robinhood", "robinhood", "fintech", "greenhouse"),
    Candidate("Samsara", "samsara", "hardware_robotics", "greenhouse"),
    Candidate("Scale AI", "scaleai", "ai_ml", "greenhouse"),
    Candidate("Semgrep", "semgrep", "cybersecurity", "ashby"),
    Candidate("Sentry", "sentry", "devtools", "ashby"),
    Candidate("SoFi", "sofi", "fintech", "greenhouse"),
    Candidate("Squarespace", "squarespace", "enterprise_saas", "greenhouse"),
    Candidate("Stitch Fix", "stitchfix", "ecommerce", "greenhouse"),
    Candidate("Stripe", "stripe", "fintech", "greenhouse"),
    Candidate("Twilio", "twilio", "devtools", "greenhouse"),
    Candidate("Upstart", "upstart", "fintech", "greenhouse"),
    Candidate("Vanta", "vanta", "cybersecurity", "ashby"),
    Candidate("Verkada", "verkada", "hardware_robotics", "greenhouse"),
    Candidate("VTS", "vts", "real_estate", "greenhouse"),
    Candidate("Watershed", "watershed", "climate_energy", "ashby"),
    Candidate("Webflow", "webflow", "enterprise_saas", "greenhouse"),
    Candidate("Wiz", "wizinc", "cybersecurity", "greenhouse"),
    Candidate("Workato", "workato", "enterprise_saas", "greenhouse"),
    Candidate("Zeta Global", "zetaglobal", "enterprise_saas", "greenhouse"),
    Candidate("Zip", "zip", "enterprise_saas", "ashby"),
    Candidate("ZocDoc", "zocdoc", "healthtech", "greenhouse"),
]

# ---------------------------------------------------------------------------
# New candidates researched to fill out industries the existing 106 barely
# touch (gaming, media_entertainment, real_estate, biotech, climate_energy,
# logistics_supply_chain, hardware_robotics, healthtech, edtech) as well as
# adding volume across the rest. Source is "auto": each token is tried
# against Greenhouse first, then Ashby, since board choice wasn't verified
# ahead of time -- only tokens that live-validate end up in the output.
# ---------------------------------------------------------------------------
NEW: list[Candidate] = [
    # gaming
    Candidate("Roblox", "roblox", "gaming"),
    Candidate("Unity", "unity", "gaming"),
    Candidate("Epic Games", "epicgames", "gaming"),
    Candidate("Riot Games", "riotgames", "gaming"),
    Candidate("Niantic", "niantic", "gaming"),
    Candidate("Scopely", "scopely", "gaming"),
    Candidate("Zynga", "zynga", "gaming"),
    Candidate("Jam City", "jamcity", "gaming"),
    Candidate("Playco", "playco", "gaming"),
    Candidate("Supercell", "supercell", "gaming"),
    Candidate("Rec Room", "recroom", "gaming"),
    Candidate("AppLovin", "applovin", "gaming"),
    Candidate("Improbable", "improbable", "gaming"),
    Candidate("Manticore Games", "manticoregames", "gaming"),
    Candidate("Wooga", "wooga", "gaming"),
    Candidate("Second Dinner", "seconddinner", "gaming"),
    # media_entertainment
    Candidate("Spotify", "spotify", "media_entertainment"),
    Candidate("Netflix", "netflix", "media_entertainment"),
    Candidate("Vimeo", "vimeo", "media_entertainment"),
    Candidate("Patreon", "patreon", "media_entertainment"),
    Candidate("Substack", "substack", "media_entertainment"),
    Candidate("BuzzFeed", "buzzfeed", "media_entertainment"),
    Candidate("Vox Media", "voxmedia", "media_entertainment"),
    Candidate("Complex Networks", "complex", "media_entertainment"),
    Candidate("SoundCloud", "soundcloud", "media_entertainment"),
    Candidate("Roku", "roku", "media_entertainment"),
    Candidate("Twitch", "twitch", "media_entertainment"),
    Candidate("Descript", "descript", "media_entertainment"),
    Candidate("Epidemic Sound", "epidemicsound", "media_entertainment"),
    Candidate("Tubi", "tubitv", "media_entertainment"),
    Candidate("Fandom", "fandom", "media_entertainment"),
    # real_estate
    Candidate("Opendoor", "opendoor", "real_estate"),
    Candidate("Compass", "urbancompass", "real_estate"),
    Candidate("Zillow", "zillow", "real_estate"),
    Candidate("Redfin", "redfin", "real_estate"),
    Candidate("Divvy Homes", "divvyhomes", "real_estate"),
    Candidate("Flyhomes", "flyhomes", "real_estate"),
    Candidate("Reonomy", "reonomy", "real_estate"),
    Candidate("HomeLight", "homelight", "real_estate"),
    Candidate("Roofstock", "roofstock", "real_estate"),
    Candidate("Doma", "doma", "real_estate"),
    Candidate("Matterport", "matterport", "real_estate"),
    Candidate("EliseAI", "eliseai", "real_estate"),
    Candidate("Placer.ai", "placerai", "real_estate"),
    Candidate("Blueground", "blueground", "real_estate"),
    Candidate("Sonder", "sonder", "real_estate"),
    # biotech
    Candidate("Ginkgo Bioworks", "ginkgobioworks", "biotech"),
    Candidate("23andMe", "23andme", "biotech"),
    Candidate("Recursion Pharmaceuticals", "recursionpharmaceuticals", "biotech"),
    Candidate("Tempus", "tempus", "biotech"),
    Candidate("Color Health", "color", "biotech"),
    Candidate("Grail", "grail", "biotech"),
    Candidate("Guardant Health", "guardanthealth", "biotech"),
    Candidate("Natera", "natera", "biotech"),
    Candidate("Invitae", "invitae", "biotech"),
    Candidate("Editas Medicine", "editasmedicine", "biotech"),
    Candidate("Beam Therapeutics", "beamtherapeutics", "biotech"),
    Candidate("Sana Biotechnology", "sanabiotechnology", "biotech"),
    Candidate("Generate Biomedicines", "generatebiomedicines", "biotech"),
    Candidate("Variant Bio", "variantbio", "biotech"),
    Candidate("Insitro", "insitro", "biotech"),
    Candidate("Freenome", "freenome", "biotech"),
    Candidate("Verve Therapeutics", "vervetherapeutics", "biotech"),
    # climate_energy
    Candidate("Aurora Solar", "aurorasolar", "climate_energy"),
    Candidate("Sunrun", "sunrun", "climate_energy"),
    Candidate("ChargePoint", "chargepoint", "climate_energy"),
    Candidate("Redwood Materials", "redwoodmaterials", "climate_energy"),
    Candidate("Form Energy", "formenergy", "climate_energy"),
    Candidate("Commonwealth Fusion Systems", "cfs", "climate_energy"),
    Candidate("Arcadia", "arcadia", "climate_energy"),
    Candidate("Span", "span", "climate_energy"),
    Candidate("Octopus Energy", "octopusenergy", "climate_energy"),
    Candidate("Sila Nanotechnologies", "silananotechnologies", "climate_energy"),
    Candidate("QuantumScape", "quantumscape", "climate_energy"),
    Candidate("Northvolt", "northvolt", "climate_energy"),
    Candidate("Crusoe Energy", "crusoeenergy", "climate_energy"),
    Candidate("Antora Energy", "antoraenergy", "climate_energy"),
    Candidate("Heirloom", "heirloom", "climate_energy"),
    # logistics_supply_chain
    Candidate("Convoy", "convoy", "logistics_supply_chain"),
    Candidate("project44", "project44", "logistics_supply_chain"),
    Candidate("FourKites", "fourkites", "logistics_supply_chain"),
    Candidate("Flock Freight", "flockfreight", "logistics_supply_chain"),
    Candidate("Deliverr", "deliverr", "logistics_supply_chain"),
    Candidate("Bringg", "bringg", "logistics_supply_chain"),
    Candidate("Freightos", "freightos", "logistics_supply_chain"),
    Candidate("Loadsmart", "loadsmart", "logistics_supply_chain"),
    Candidate("ShipBob", "shipbobinc", "logistics_supply_chain"),
    Candidate("Motive", "motive", "logistics_supply_chain"),
    Candidate("Stord", "stord", "logistics_supply_chain"),
    Candidate("Onfleet", "onfleet", "logistics_supply_chain"),
    # hardware_robotics
    Candidate("Anduril", "anduril", "hardware_robotics"),
    Candidate("Zipline", "zipline", "hardware_robotics"),
    Candidate("Skydio", "skydio", "hardware_robotics"),
    Candidate("Shield AI", "shieldai", "hardware_robotics"),
    Candidate("Cruise", "cruise", "hardware_robotics"),
    Candidate("Aurora Innovation", "aurorainnovation", "hardware_robotics"),
    Candidate("Nuro", "nuro", "hardware_robotics"),
    Candidate("Rivian", "rivian", "hardware_robotics"),
    Candidate("Boston Dynamics", "bostondynamics", "hardware_robotics"),
    Candidate("iRobot", "irobot", "hardware_robotics"),
    Candidate("Bird", "bird", "hardware_robotics"),
    Candidate("Lime", "lime", "hardware_robotics"),
    Candidate("Waymo", "waymo", "hardware_robotics"),
    Candidate("Applied Intuition", "appliedintuition", "hardware_robotics"),
    Candidate("Figure AI", "figure", "hardware_robotics"),
    Candidate("Physical Intelligence", "physicalintelligence", "hardware_robotics"),
    # healthtech
    Candidate("Ro", "ro", "healthtech"),
    Candidate("Hims & Hers", "hims", "healthtech"),
    Candidate("Included Health", "includedhealth", "healthtech"),
    Candidate("Devoted Health", "devotedhealth", "healthtech"),
    Candidate("Clover Health", "cloverhealth", "healthtech"),
    Candidate("Carbon Health", "carbonhealth", "healthtech"),
    Candidate("Maven Clinic", "mavenclinic", "healthtech"),
    Candidate("Cityblock Health", "cityblockhealth", "healthtech"),
    Candidate("Sword Health", "swordhealth", "healthtech"),
    Candidate("Hinge Health", "hingehealth", "healthtech"),
    Candidate("Cedar", "cedar", "healthtech"),
    Candidate("Doximity", "doximity", "healthtech"),
    Candidate("Omada Health", "omadahealth", "healthtech"),
    Candidate("Virta Health", "virtahealth", "healthtech"),
    Candidate("Modern Health", "modernhealth", "healthtech"),
    Candidate("Lyra Health", "lyrahealth", "healthtech"),
    Candidate("Spring Health", "springhealth", "healthtech"),
    Candidate("Amwell", "amwell", "healthtech"),
    Candidate("Talkspace", "talkspace", "healthtech"),
    Candidate("Headway", "headway", "healthtech"),
    Candidate("Alto Pharmacy", "altopharmacy", "healthtech"),
    Candidate("Truepill", "truepill", "healthtech"),
    Candidate("Thirty Madison", "thirtymadison", "healthtech"),
    Candidate("Cerebral", "cerebral", "healthtech"),
    # edtech
    Candidate("Duolingo", "duolingo", "edtech"),
    Candidate("Guild Education", "guildeducation", "edtech"),
    Candidate("Course Hero", "coursehero", "edtech"),
    Candidate("Chegg", "chegg", "edtech"),
    Candidate("Outschool", "outschool", "edtech"),
    Candidate("ClassDojo", "classdojo", "edtech"),
    Candidate("Nearpod", "nearpod", "edtech"),
    Candidate("IXL Learning", "ixllearning", "edtech"),
    Candidate("2U", "2u", "edtech"),
    Candidate("Udemy", "udemy", "edtech"),
    Candidate("Skillshare", "skillshare", "edtech"),
    Candidate("Codecademy", "codecademy", "edtech"),
    Candidate("Age of Learning", "ageoflearning", "edtech"),
    Candidate("Khan Academy", "khanacademy", "edtech"),
    # consumer
    Candidate("Strava", "strava", "consumer"),
    Candidate("Headspace", "headspace", "consumer"),
    Candidate("Calm", "calm", "consumer"),
    Candidate("Cameo", "cameo", "consumer"),
    Candidate("Bumble", "bumble", "consumer"),
    Candidate("Whoop", "whoop", "consumer"),
    Candidate("Thumbtack", "thumbtack", "consumer"),
    Candidate("Rover", "rover", "consumer"),
    Candidate("Life360", "life360", "consumer"),
    Candidate("Angi", "angi", "consumer"),
    # ecommerce
    Candidate("Shopify", "shopify", "ecommerce"),
    Candidate("Klaviyo", "klaviyo", "ecommerce"),
    Candidate("Recharge", "recharge", "ecommerce"),
    Candidate("Postscript", "postscript", "ecommerce"),
    Candidate("Yotpo", "yotpo", "ecommerce"),
    Candidate("Gorgias", "gorgias", "ecommerce"),
    Candidate("Loop Returns", "loopreturns", "ecommerce"),
    Candidate("Bloomreach", "bloomreach", "ecommerce"),
    Candidate("Wayfair", "wayfair", "ecommerce"),
    Candidate("Chewy", "chewy", "ecommerce"),
    Candidate("Poshmark", "poshmark", "ecommerce"),
    Candidate("OfferUp", "offerup", "ecommerce"),
    Candidate("BigCommerce", "bigcommerce", "ecommerce"),
    Candidate("Fanatics", "fanatics", "ecommerce"),
    # enterprise_saas
    Candidate("Zendesk", "zendesk", "enterprise_saas"),
    Candidate("HubSpot", "hubspot", "enterprise_saas"),
    Candidate("Smartsheet", "smartsheet", "enterprise_saas"),
    Candidate("monday.com", "monday", "enterprise_saas"),
    Candidate("ClickUp", "clickup", "enterprise_saas"),
    Candidate("Coda", "coda", "enterprise_saas"),
    Candidate("Miro", "miro", "enterprise_saas"),
    Candidate("Loom", "loom", "enterprise_saas"),
    Candidate("Calendly", "calendly", "enterprise_saas"),
    Candidate("DocuSign", "docusign", "enterprise_saas"),
    Candidate("PandaDoc", "pandadoc", "enterprise_saas"),
    Candidate("Gong", "gong", "enterprise_saas"),
    Candidate("Outreach", "outreach", "enterprise_saas"),
    Candidate("SalesLoft", "salesloft", "enterprise_saas"),
    Candidate("Drift", "drift", "enterprise_saas"),
    Candidate("Front", "front", "enterprise_saas"),
    Candidate("Freshworks", "freshworks", "enterprise_saas"),
    Candidate("Rippling", "rippling", "enterprise_saas"),
    Candidate("Canva", "canva", "enterprise_saas"),
    # devtools
    Candidate("HashiCorp", "hashicorp", "devtools"),
    Candidate("Vercel", "vercel", "devtools"),
    Candidate("Netlify", "netlify", "devtools"),
    Candidate("Render", "render", "devtools"),
    Candidate("Fly.io", "flyio", "devtools"),
    Candidate("Supabase", "supabase", "devtools"),
    Candidate("Prisma", "prisma", "devtools"),
    Candidate("Temporal", "temporal", "devtools"),
    Candidate("Grafana Labs", "grafanalabs", "devtools"),
    Candidate("Honeycomb", "honeycomb", "devtools"),
    Candidate("Sourcegraph", "sourcegraph", "devtools"),
    Candidate("Gitpod", "gitpod", "devtools"),
    Candidate("JFrog", "jfrog", "devtools"),
    Candidate("Buildkite", "buildkite", "devtools"),
    Candidate("Harness", "harness", "devtools"),
    Candidate("Codecov", "codecov", "devtools"),
    Candidate("Cypress", "cypress", "devtools"),
    Candidate("dbt Labs", "dbtlabs", "devtools"),
    Candidate("Airbyte", "airbyte", "devtools"),
    Candidate("Census", "census", "devtools"),
    Candidate("Hightouch", "hightouch", "devtools"),
    Candidate("Metabase", "metabase", "devtools"),
    Candidate("Mode Analytics", "mode", "devtools"),
    Candidate("Materialize", "materialize", "devtools"),
    Candidate("RudderStack", "rudderstack", "devtools"),
    Candidate("mParticle", "mparticle", "devtools"),
    # ai_ml
    Candidate("Hugging Face", "huggingface", "ai_ml"),
    Candidate("Cohere", "cohere", "ai_ml"),
    Candidate("Stability AI", "stabilityai", "ai_ml"),
    Candidate("Runway", "runwayml", "ai_ml"),
    Candidate("Character.AI", "characterai", "ai_ml"),
    Candidate("Together AI", "togetherai", "ai_ml"),
    Candidate("Anyscale", "anyscale", "ai_ml"),
    Candidate("Modal", "modal", "ai_ml"),
    Candidate("Replicate", "replicate", "ai_ml"),
    Candidate("Glean", "glean", "ai_ml"),
    Candidate("Writer", "getwriter", "ai_ml"),
    Candidate("Harvey", "harvey", "ai_ml"),
    Candidate("Sierra", "sierra", "ai_ml"),
    Candidate("Cresta", "cresta", "ai_ml"),
    Candidate("Weights & Biases", "wandb", "ai_ml"),
    Candidate("ElevenLabs", "elevenlabs", "ai_ml"),
    Candidate("Anysphere", "anysphere", "ai_ml"),
    Candidate("Adept", "adept", "ai_ml"),
    Candidate("Inflection AI", "inflectionai", "ai_ml"),
    # cybersecurity
    Candidate("CrowdStrike", "crowdstrike", "cybersecurity"),
    Candidate("SentinelOne", "sentinelone", "cybersecurity"),
    Candidate("Netskope", "netskope", "cybersecurity"),
    Candidate("Zscaler", "zscaler", "cybersecurity"),
    Candidate("Tanium", "tanium", "cybersecurity"),
    Candidate("Rapid7", "rapid7", "cybersecurity"),
    Candidate("Tenable", "tenable", "cybersecurity"),
    Candidate("Lacework", "lacework", "cybersecurity"),
    Candidate("Orca Security", "orcasecurity", "cybersecurity"),
    Candidate("Drata", "drata", "cybersecurity"),
    Candidate("Secureframe", "secureframe", "cybersecurity"),
    Candidate("1Password", "1password", "cybersecurity"),
    Candidate("Snyk", "snyk", "cybersecurity"),
    Candidate("KnowBe4", "knowbe4", "cybersecurity"),
    Candidate("Ping Identity", "pingidentity", "cybersecurity"),
    # fintech
    Candidate("Plaid", "plaid", "fintech"),
    Candidate("Wealthfront", "wealthfront", "fintech"),
    Candidate("Addepar", "addepar", "fintech"),
    Candidate("Klarna", "klarna", "fintech"),
    Candidate("Melio", "melio", "fintech"),
    Candidate("Mercury", "mercury", "fintech"),
    Candidate("Truework", "truework", "fintech"),
    Candidate("Pilot", "pilot", "fintech"),
    Candidate("Deel", "deel", "fintech"),
    Candidate("Unit", "unit", "fintech"),
    Candidate("Highnote", "highnote", "fintech"),
    Candidate("Moov", "moov", "fintech"),
    Candidate("Increase", "increase", "fintech"),
]

# ---------------------------------------------------------------------------
# Second pass: candidates researched via web search, with board tokens
# confirmed directly from live boards.greenhouse.io / jobs.ashbyhq.com URLs
# (rather than guessed) -- added to fill out categories the first pass left
# thin (real_estate, climate_energy, logistics_supply_chain,
# media_entertainment, hardware_robotics, gaming, biotech). Source is fixed
# since the host is known from the URL that was found.
# ---------------------------------------------------------------------------
RESEARCHED: list[Candidate] = [
    # real_estate
    Candidate("Entera", "entera", "real_estate", "greenhouse"),
    Candidate("Ownwell", "ownwell", "real_estate", "greenhouse"),
    Candidate("Revive", "revivecareers", "real_estate", "greenhouse"),
    Candidate("SmartRent", "smartrent", "real_estate", "greenhouse"),
    Candidate("Kiavi", "kiavi", "real_estate", "greenhouse"),
    # climate_energy
    Candidate("David Energy", "davidenergy", "climate_energy", "ashby"),
    Candidate("Climatiq", "climatiq", "climate_energy", "ashby"),
    Candidate("Antares", "antares", "climate_energy", "ashby"),
    Candidate("Gravity Climate", "GravityClimate", "climate_energy", "ashby"),
    # logistics_supply_chain
    Candidate("Grover", "grover", "logistics_supply_chain", "greenhouse"),
    Candidate("Weee!", "weee", "logistics_supply_chain", "greenhouse"),
    Candidate("Feather", "feather", "logistics_supply_chain", "greenhouse"),
    Candidate("Choco", "choco", "logistics_supply_chain", "greenhouse"),
    # ecommerce
    Candidate("Who Gives A Crap", "whogivesacrap", "ecommerce", "greenhouse"),
    Candidate("StockX", "stockx", "ecommerce", "greenhouse"),
    # media_entertainment
    Candidate("Team Whistle", "whistlesports", "media_entertainment", "greenhouse"),
    Candidate(
        "Sony Music Entertainment", "sonymusic", "media_entertainment", "greenhouse"
    ),
    # hardware_robotics
    Candidate("Built Robotics", "built-robotics", "hardware_robotics", "ashby"),
    Candidate("Bedrock Robotics", "bedrock-robotics", "hardware_robotics", "ashby"),
    Candidate("Dyna Robotics", "dyna-robotics", "hardware_robotics", "ashby"),
    Candidate("Foundry Robotics", "foundry-robotics", "hardware_robotics", "ashby"),
    Candidate("Orchard Robotics", "orchard", "hardware_robotics", "ashby"),
    # biotech
    Candidate("Genomics", "genomics", "biotech", "ashby"),
    Candidate("Basecamp Research", "basecamp-research", "biotech", "ashby"),
    # gaming
    Candidate("Rockstar Games", "rockstargames", "gaming", "greenhouse"),
    Candidate("NetEase Games", "neteasegames", "gaming", "greenhouse"),
    Candidate("2K", "2k", "gaming", "greenhouse"),
    Candidate("Mythical Games", "mythicalgames", "gaming", "greenhouse"),
    Candidate("Volley", "volleythat", "gaming", "greenhouse"),
    Candidate("Stellar Entertainment", "stellarentertainment", "gaming", "ashby"),
]

ALL_CANDIDATES: list[Candidate] = EXISTING + NEW + RESEARCHED


@dataclass
class Result:
    candidate: Candidate
    kept: bool
    source: str | None  # the source that actually validated, if kept
    reason: str  # human-readable outcome, used in the summary print


_RATE_LIMIT_RETRIES = 3


async def _get_with_retry(
    url: str, client: httpx.AsyncClient, timeout: float
) -> httpx.Response:
    """GET with a short backoff on 429 so bursty concurrency doesn't cause
    false negatives (a rate-limited real company looking like a dead one)."""
    for attempt in range(_RATE_LIMIT_RETRIES):
        resp = await client.get(url, timeout=timeout)
        if resp.status_code != 429:
            return resp
        await asyncio.sleep(1.5 * (attempt + 1))
    return resp


async def _try_greenhouse(token: str, client: httpx.AsyncClient, timeout: float) -> int:
    resp = await _get_with_retry(_GREENHOUSE_URL.format(token=token), client, timeout)
    if resp.status_code != 200:
        return 0
    return len(resp.json().get("jobs", []))


async def _try_ashby(token: str, client: httpx.AsyncClient, timeout: float) -> int:
    resp = await _get_with_retry(_ASHBY_URL.format(token=token), client, timeout)
    if resp.status_code != 200:
        return 0
    return len(resp.json().get("jobs", []))


async def _validate_one(
    candidate: Candidate, client: httpx.AsyncClient, timeout: float
) -> Result:
    sources_to_try = (
        [candidate.source] if candidate.source != "auto" else ["greenhouse", "ashby"]
    )
    last_reason = "unreachable"
    for source in sources_to_try:
        fetcher = _try_greenhouse if source == "greenhouse" else _try_ashby
        try:
            count = await fetcher(candidate.board_token, client, timeout)
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            last_reason = f"{source}: {exc.__class__.__name__}"
            continue
        if count > 0:
            return Result(candidate, True, source, f"{source}: {count} jobs")
        last_reason = f"{source}: no jobs (or 404)"
    return Result(candidate, False, None, last_reason)


async def validate_all(
    candidates: list[Candidate], *, concurrency: int = 10, timeout: float = 12.0
) -> list[Result]:
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=concurrency, max_keepalive_connections=concurrency
    )

    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:

        async def guarded(candidate: Candidate) -> Result:
            async with sem:
                return await _validate_one(candidate, client, timeout)

        return await asyncio.gather(*(guarded(c) for c in candidates))


def _format_row(company: str, source: str, token: str, industry: str) -> str:
    row = {
        "company": company,
        "source": source,
        "board_token": token,
        "industry": industry,
    }
    dumped = yaml.safe_dump(
        row, default_flow_style=True, sort_keys=False, width=1000
    ).strip()
    return "- " + dumped


def write_yaml(kept: list[Result]) -> None:
    rows = sorted(kept, key=lambda r: r.candidate.company.lower())
    lines = [_HEADER]
    for r in rows:
        assert r.source is not None
        lines.append(
            _format_row(
                r.candidate.company,
                r.source,
                r.candidate.board_token,
                r.candidate.industry,
            )
        )
    _OUTPUT_PATH.write_text("\n".join(lines) + "\n")


async def main() -> None:
    print(
        f"Validating {len(ALL_CANDIDATES)} candidates "
        f"({len(EXISTING)} existing + {len(NEW)} new + {len(RESEARCHED)} researched)..."
    )
    start = time.monotonic()
    results = await validate_all(ALL_CANDIDATES)
    elapsed = time.monotonic() - start

    kept = [r for r in results if r.kept]
    dropped = [r for r in results if not r.kept]

    print(f"\nDone in {elapsed:.1f}s.")
    print(f"Kept:    {len(kept)}")
    print(f"Dropped: {len(dropped)}")
    print("\n--- dropped (company: reason) ---")
    for r in sorted(dropped, key=lambda r: r.candidate.company.lower()):
        print(f"  {r.candidate.company}: {r.reason}")

    print("\n--- industry distribution (kept) ---")
    counts: dict[str, int] = {}
    for r in kept:
        counts[r.candidate.industry] = counts.get(r.candidate.industry, 0) + 1
    for industry, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {industry}: {n}")

    write_yaml(kept)
    print(f"\nWrote {len(kept)} entries to {_OUTPUT_PATH}")


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
