# Node-pool options establish exact OKE-version/ARM eligibility; Compute independently filters
# actual shape, OS family and lifecycle and provides creation timestamps for deterministic choice.
data "oci_core_images" "node" {
  compartment_id           = var.compartment_ocid
  shape                    = "VM.Standard.A1.Flex"
  operating_system         = "Oracle Linux"
  operating_system_version = var.oke.node_os_major
  state                    = "AVAILABLE"
  sort_by                  = "TIMECREATED"
  sort_order               = "DESC"
}

# Deduplicate IDs before comparison. Conflicting duplicates and invalid timestamps are excluded
# rather than resolved by response order; a malformed eligible row fails the precondition below.
locals {
  oke_image_ids = toset([for source in data.oci_containerengine_node_pool_option.supported.sources : source.image_id if source.source_type == "IMAGE"])
  eligible_image_rows = [for image in data.oci_core_images.node.images : image if(
    contains(local.oke_image_ids, image.id) && image.operating_system == "Oracle Linux" &&
    image.operating_system_version == var.oke.node_os_major && image.state == "AVAILABLE"
  )]
  image_rows_by_id = { for image in local.eligible_image_rows : image.id => image... }
  eligible_images = [for image_id, rows in local.image_rows_by_id : rows[0] if(
    length(toset([for row in rows : row.time_created])) == 1 && can(timecmp(rows[0].time_created, rows[0].time_created))
  )]
  newest_images = [for image in local.eligible_images : image if alltrue([
    for other in local.eligible_images : timecmp(image.time_created, other.time_created) >= 0
  ])]
  selected_candidates = var.qualified_node_image == null ? local.newest_images : [
    for image in local.eligible_images : image if image.id == var.qualified_node_image.image_ocid
  ]
  selected_image = try(one(local.selected_candidates), null)
}

