from app.verification.response_guard import ResponseGuard


def test_short_brand_and_model_name_counts_as_citing_selected_product():
    selected = {
        "product_id": "p1", "brand": "小米",
        "title": "小米Redmi Buds 5 Pro真无线降噪耳机Hi-Res金标认证12mm动圈",
    }
    variant = {
        "product_id": "p2", "brand": "小米",
        "title": "小米Redmi Buds 5 Pro真无线降噪耳机Hi-Res金标认证10mm动圈",
    }

    assert ResponseGuard()._check_cited_in_list(
        "首选小米 Redmi Buds 5 Pro，299元适合通勤。", [selected, variant], ["p1"]
    )


def test_brand_alone_does_not_count_as_product_citation():
    product = {"product_id": "p1", "brand": "小米", "title": "小米Redmi Buds 5 Pro真无线降噪耳机"}

    assert not ResponseGuard()._check_cited_in_list("小米的耳机可以考虑。", [product], ["p1"])
