mock_provider "oci" {
  override_during = plan
}

override_resource {
  override_during = plan
  target          = oci_identity_domains_rule.atlas["discover"]
  values          = { id = "discover-rule" }
}

override_resource {
  override_during = plan
  target          = oci_identity_domains_rule.atlas["allow"]
  values          = { id = "allow-rule" }
}

override_resource {
  override_during = plan
  target          = oci_identity_domains_rule.atlas["deny"]
  values          = { id = "deny-rule" }
}

variables {
  environment         = "development"
  identity_domain_url = "https://idcs-example.identity.oraclecloud.com"
  corporate_idp_id    = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}

run "development" {
  command = plan

  assert {
    condition     = oci_identity_domains_policy.idp.name == "otm-development-idp" && oci_identity_domains_policy.signon.name == "otm-development-sign-on"
    error_message = "Give both Atlas policies unique development names."
  }

  assert {
    condition = (
      oci_identity_domains_condition.atlas["discover"].attribute_name == "operation" &&
      oci_identity_domains_condition.atlas["discover"].attribute_value == "IDP Discovery" &&
      tomap({ for result in oci_identity_domains_rule.atlas["discover"].return : result.name => result.value }) == tomap({
        userChoice = "false", LocalIDPs = "[]", SamlIDPs = jsonencode([var.corporate_idp_id]), SocialIDPs = "[]", X509IDPs = "[]"
      }) &&
      oci_identity_domains_policy.idp.active &&
      oci_identity_domains_policy.idp.rules[0].sequence == 1 &&
      oci_identity_domains_policy.idp.rules[0].value == "discover-rule"
    )
    error_message = "Discovery must offer only the approved upstream provider."
  }

  assert {
    condition = (
      oci_identity_domains_condition.atlas["allow"].attribute_name == "subject.authenticatedBy" &&
      oci_identity_domains_condition.atlas["allow"].operator == "in" &&
      oci_identity_domains_condition.atlas["allow"].attribute_value == jsonencode([var.corporate_idp_id]) &&
      tomap({ for result in oci_identity_domains_rule.atlas["allow"].return : result.name => result.value }) == tomap({
        effect = "ALLOW", reAuthenticate = "true", authenticationFactor = "IDP"
      }) &&
      oci_identity_domains_condition.atlas["deny"].attribute_name == "target.action" &&
      oci_identity_domains_condition.atlas["deny"].attribute_value == jsonencode("Login") &&
      oci_identity_domains_rule.atlas["deny"].return[0].value == "DENY" &&
      oci_identity_domains_policy.signon.active &&
      [for rule in oci_identity_domains_policy.signon.rules : rule.sequence] == [1, 2] &&
      [for rule in oci_identity_domains_policy.signon.rules : rule.value] == ["allow-rule", "deny-rule"]
    )
    error_message = "Sign-on must require fresh corporate authentication before denying other sign-in."
  }
}

run "staging" {
  command = plan

  variables {
    environment = "staging"
  }

  assert {
    condition     = oci_identity_domains_policy.idp.name == "otm-staging-idp" && oci_identity_domains_policy.signon.name == "otm-staging-sign-on"
    error_message = "Staging must have policy names distinct from development in the same domain."
  }
}

run "production" {
  command = plan

  variables {
    environment         = "production"
    identity_domain_url = "https://idcs-production.identity.oraclecloud.com"
    corporate_idp_id    = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  }

  assert {
    condition = (
      oci_identity_domains_policy.idp.name == "otm-production-idp" &&
      oci_identity_domains_policy.signon.name == "otm-production-sign-on" &&
      oci_identity_domains_policy.signon.idcs_endpoint == var.identity_domain_url &&
      oci_identity_domains_condition.atlas["allow"].attribute_value == jsonencode([var.corporate_idp_id])
    )
    error_message = "Production must bind its own environment and upstream provider."
  }
}

run "reject_non_domain_endpoint" {
  command = plan

  variables {
    identity_domain_url = "https://idcs-example.identity.oraclecloud.com/unexpected"
  }

  expect_failures = [var.identity_domain_url]
}
