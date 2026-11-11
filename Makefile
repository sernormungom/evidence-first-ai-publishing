PYTHON ?= python3
.DEFAULT_GOAL := help
help:
	@echo 'make demo | demo-check | test | validate | preview | site | disclosure-check'
	@echo 'Optional: make draft ARTICLE=... DRY_RUN=1; make translate ARTICLE=... DRY_RUN=1'
demo:
	$(PYTHON) scripts/portfolio.py
validate:
	$(PYTHON) scripts/validate.py
preview:
	$(PYTHON) scripts/build.py --allow-unverified
site: validate preview
	$(PYTHON) scripts/build_site.py
publish: validate
	$(PYTHON) scripts/build.py
test:
	$(PYTHON) -m unittest discover -s scripts/tests
	$(PYTHON) -m unittest discover -s skills/handbook-section/scripts -p 'test_*.py'
demo-check: test
review:
	$(PYTHON) scripts/make_review_sheet.py $(ARTICLE)
draft:
	$(PYTHON) scripts/draft.py $(if $(DRY_RUN),--dry-run) $(ARTICLE)
translate:
	$(PYTHON) scripts/translate.py $(if $(DRY_RUN),--dry-run) $(ARTICLE)
recover-draft:
	$(PYTHON) scripts/draft.py --response-file "$(RESPONSE)" "$(ARTICLE)"
recover-translation:
	$(PYTHON) scripts/translate.py --response-file "$(RESPONSE)" "$(ARTICLE)"
harvest:
	$(PYTHON) scripts/harvest.py
disclosure-check:
	$(PYTHON) scripts/disclosure_check.py
.PHONY: help demo demo-check test validate preview site publish review draft translate recover-draft recover-translation harvest disclosure-check
