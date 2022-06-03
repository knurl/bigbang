resource "aws_s3_bucket" "s3_bucket" {
  bucket        = var.bucket_name
  force_destroy = true
  tags          = var.tags
}

resource "aws_s3_bucket_acl" "s3_bucket_acl" {
  bucket = aws_s3_bucket.s3_bucket.id
  acl    = "private"
}

data "aws_iam_policy_document" "bucket_access_policy_doc" {
  statement {
    principals {
      type        = "AWS"
      identifiers = [module.eks.eks_managed_node_groups["ng"].iam_role_arn]
    }

    actions = ["s3:*"]

    effect = "Allow"

    resources = [
      aws_s3_bucket.s3_bucket.arn,
      "${aws_s3_bucket.s3_bucket.arn}/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "aws:SourceVpc"
      values   = ["${module.vpc.vpc_id}"]
    }
  }
}

resource "aws_s3_bucket_policy" "bucket_access_policy" {
  bucket = aws_s3_bucket.s3_bucket.id
  policy = data.aws_iam_policy_document.bucket_access_policy_doc.json
}
