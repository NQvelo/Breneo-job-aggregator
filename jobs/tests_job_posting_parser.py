"""Tests for job_posting_parser (incl. non-English section headings)."""

from django.test import TestCase

from jobs.job_posting_parser import parse_job_posting_for_db


class GeorgianJobPostingParserTests(TestCase):
    def test_splits_role_and_requirements_sections(self):
        text = """
შენი როლი თინეთში:

** Back-end სტანდარტების დაცვა;

** PHP-ზე სუფთა კოდის წერა;

ეს ვაკანსია შენთვისაა, თუ გაქვს:

** მინიმუმ 4 წლიანი გამოცდილება;

** PHP-ის სიღრმისეული ცოდნა და პრაქტიკული გამოცდილება;

თინეთში დაგხვდება:

** ჯანმრთელობის დაზღვევა;
"""
        out = parse_job_posting_for_db(text)
        self.assertIn("Back-end", out["responsibilities"])
        self.assertIn("PHP-ზე", out["responsibilities"])
        self.assertIn("4 წლიანი", out["qualifications"])
        self.assertIn("PHP-ის", out["qualifications"])
        self.assertGreaterEqual(len([ln for ln in out["qualifications"].split("\n") if ln.strip()]), 2)
        self.assertNotIn("დაზღვევა", out["responsibilities"])
        self.assertNotIn("დაზღვევა", out["qualifications"])

    def test_jobs_ge_headings_and_short_bullets(self):
        text = """"EPAM" ეძებს Senior AI Agent Engineer-ს.

რას გააკეთებ:

• შექმნი და მართავ აგენტურ სისტემებს;
• იმუშავებ უშუალოდ მომხმარებლებთან.

ვის ვეძებთ:

• უმაღლესი განათლება;
• ინგლისური ენის ცოდნა B2+ დონეზე.

პროგრამირების კონკრეტულ ენას არ ვზღუდავთ.
"""
        out = parse_job_posting_for_db(text)
        self.assertEqual(
            out["responsibilities"],
            "• შექმნი და მართავ აგენტურ სისტემებს;\n• იმუშავებ უშუალოდ მომხმარებლებთან.",
        )
        self.assertEqual(
            out["qualifications"],
            "• უმაღლესი განათლება;\n• ინგლისური ენის ცოდნა B2+ დონეზე.",
        )

    def test_schedule_pay_and_apply_text_not_in_qualifications(self):
        text = """მოთხოვნები:

** ხელისა და ელექტროინსტრუმენტებთან მუშაობის გამოცდილება;
** სმარტფონი Android 10 ან უფრო ახალი ვერსიით.

სამუშაო გრაფიკი:

** კვირაში 6 სამუშაო და 1 დასვენების დღე;
** 8-საათიანი სამუშაო ცვლა;

ანაზღაურება:

** სტაჟირების პერიოდში (1 თვემდე) — 65 ლარი/ცვლა

ველოდებით თქვენს CV-ის: hr@example.com
აუცილებლად მიუთითეთ რომელ ვაკანსიაზე აგზავნით!
"""
        out = parse_job_posting_for_db(text)
        self.assertEqual(
            out["qualifications"],
            "• ხელისა და ელექტროინსტრუმენტებთან მუშაობის გამოცდილება;\n"
            "• სმარტფონი Android 10 ან უფრო ახალი ვერსიით.",
        )

    def test_trailing_apply_prose_after_bullets_dropped(self):
        text = """მოთხოვნები:

** უმაღლესი განათლება;
** მაღალი პასუხისმგებლობა.

მონაცემები (CV) გამოაგზავნეთ ელექტრონული ფოსტის მისამართზე hr@example.com. გთხოვთ, Subject-ში მიუთითეთ პოზიციის დასახელება.
"""
        out = parse_job_posting_for_db(text)
        self.assertEqual(out["qualifications"], "• უმაღლესი განათლება;\n• მაღალი პასუხისმგებლობა.")


class JobsGeBodyTextTests(TestCase):
    def test_drops_header_rows_and_keeps_inline_text_on_one_line(self):
        from bs4 import BeautifulSoup

        from jobs.fetchers import _jobs_ge_body_text

        html = """
<table class="dtable">
  <tr><td class="dtitle"><span>დასახელება:</span> <b>ტექნიკოსი</b></td></tr>
  <tr><td class="dtitle"><span>მომწოდებელი:</span> <b><a href="#">JET</a></b></td></tr>
  <tr><td>
    <b>"JET"</b> ვეძებთ <b>ტექნიკოსს</b>.<br />
<br />
მოთხოვნები:<br />
** პრობლემის აღმოფხვრა ან<br />
ესკალირება;<br />
** სტაჟირება — <b>65 ლარი</b>, კვალიფიკაციის შესაბამისად.<br />
<br />
განცხადების სრულად ნახვა შესაძლებელია <a href="#">ინგლისურ ენაზე</a>.
  </td></tr>
</table>"""
        text = _jobs_ge_body_text(BeautifulSoup(html, "html.parser"))
        self.assertEqual(
            text,
            '"JET" ვეძებთ ტექნიკოსს.\n\n'
            "მოთხოვნები:\n"
            "• პრობლემის აღმოფხვრა ან ესკალირება;\n"
            "• სტაჟირება — 65 ლარი, კვალიფიკაციის შესაბამისად.",
        )
