from django.test import Client, TestCase
from django.urls import reverse

from .models import RAMModule


class CompareToggleTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.module = RAMModule.objects.create(
            name='Test Module', brand='TestBrand', capacity_gb=8
        )
        self.url = reverse(
            'products:compare_toggle', kwargs={'pk': self.module.pk}
        )

    def test_toggle_add(self):
        """POST с пустой сессией добавляет pk."""
        resp = self.client.post(self.url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['ids'], [self.module.pk])
        self.assertEqual(data['count'], 1)
        self.assertEqual(self.client.session['compare_ids'], [self.module.pk])

    def test_toggle_remove(self):
        """Повторный POST удаляет pk."""
        session = self.client.session
        session['compare_ids'] = [self.module.pk]
        session.save()
        resp = self.client.post(self.url)
        self.assertEqual(resp.json()['ids'], [])
        self.assertEqual(self.client.session['compare_ids'], [])

    def test_toggle_limit(self):
        """При 4 id в сессии новый pk не добавляется (R3)."""
        others = [
            RAMModule.objects.create(name=f'M{i}', brand='B', capacity_gb=4)
            for i in range(4)
        ]
        session = self.client.session
        session['compare_ids'] = [m.pk for m in others]
        session.save()
        resp = self.client.post(self.url)
        data = resp.json()
        self.assertNotIn(self.module.pk, data['ids'])
        self.assertEqual(data['count'], 4)

    def test_toggle_get_not_allowed(self):
        """GET → 405."""
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)

    def test_toggle_csrf(self):
        """POST без CSRF-токена → 403."""
        c = Client(enforce_csrf_checks=True)
        resp = c.post(self.url)
        self.assertEqual(resp.status_code, 403)


class CompareClearTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('products:compare_clear')

    def test_clear_resets_session_and_redirects(self):
        """POST очищает сессию и редиректит на каталог."""
        module = RAMModule.objects.create(name='M', brand='B', capacity_gb=8)
        session = self.client.session
        session['compare_ids'] = [module.pk]
        session.save()
        resp = self.client.post(self.url)
        self.assertRedirects(resp, reverse('products:product_list'))
        self.assertEqual(self.client.session.get('compare_ids', []), [])

    def test_clear_get_not_allowed(self):
        """GET → 405."""
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 405)


class CompareViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('products:compare')
        self.m1 = RAMModule.objects.create(name='M1', brand='B', capacity_gb=8)
        self.m2 = RAMModule.objects.create(
            name='M2', brand='B', capacity_gb=16
        )

    def _set_session(self, ids):
        session = self.client.session
        session['compare_ids'] = ids
        session.save()

    def test_compare_shows_modules_from_session(self):
        """Сессия [m1, m2] → оба модуля видны на странице (R6)."""
        self._set_session([self.m1.pk, self.m2.pk])
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'M1')
        self.assertContains(resp, 'M2')

    def test_compare_single_module_shows_error(self):
        """Сессия [m1] → сообщение об ошибке."""
        self._set_session([self.m1.pk])
        resp = self.client.get(self.url)
        self.assertContains(resp, 'Выберите от 2 до 4')

    def test_compare_empty_session_shows_error(self):
        """Пустая сессия → сообщение об ошибке."""
        resp = self.client.get(self.url)
        self.assertContains(resp, 'Выберите от 2 до 4')

    def test_compare_prunes_stale_ids(self):
        """Удалённый id убирается со страницы, сессия перезаписывается (R8)."""
        self._set_session([self.m1.pk, self.m2.pk, 99999])
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(99999, self.client.session['compare_ids'])
        self.assertIn(self.m1.pk, self.client.session['compare_ids'])

    def test_compare_has_clear_button(self):
        """На странице /compare/ есть кнопка «Очистить список» (R7)."""
        self._set_session([self.m1.pk, self.m2.pk])
        resp = self.client.get(self.url)
        self.assertContains(resp, 'Очистить список')

    def test_ids_param_ignored(self):
        """?ids= в URL больше не влияет на список сравнения (R6)."""
        self._set_session([self.m1.pk])
        resp = self.client.get(self.url + f'?ids={self.m2.pk}')
        self.assertNotContains(resp, 'M2')


class ProductListCompareTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.url = reverse('products:product_list')
        self.module = RAMModule.objects.create(
            name='TestMod', brand='B', capacity_gb=8
        )

    def test_checked_checkbox_from_session(self):
        """Сессия [module.pk] → чекбокс отмечен при рендере (R4)."""
        session = self.client.session
        session['compare_ids'] = [self.module.pk]
        session.save()
        resp = self.client.get(self.url)
        self.assertContains(resp, 'checked')

    def test_no_compare_form_or_submit(self):
        """Рендер не содержит #compare-form и #compare-submit (KTD7)."""
        resp = self.client.get(self.url)
        self.assertNotContains(resp, 'compare-form')
        self.assertNotContains(resp, 'compare-submit')

    def test_data_toggle_url_present(self):
        """Чекбоксы содержат data-toggle-url для AJAX-запроса (KTD8)."""
        resp = self.client.get(self.url)
        self.assertContains(resp, 'data-toggle-url')
