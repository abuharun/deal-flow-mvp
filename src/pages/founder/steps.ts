import type { StepKey } from '../../lib/types'

interface StepMeta {
  title: string
  question: string
  hint: string
  placeholder: string
}

export const STEP_META: Record<StepKey, StepMeta> = {
  problem: {
    title: 'Muammo',
    question: 'Qanday muammoni va kim uchun hal qilasiz?',
    hint: "Aniq yozing: bu og'riqni kim, qanchalik tez-tez his qiladi va bu unga bugun qanchaga tushadi. Oddiy so'zlar pitch tilidan kuchliroq.",
    placeholder:
      "Masalan: Toshkentdagi restoranlar mahsulotni bozordan telefon qo'ng'irog'i va naqd pul bilan sotib oladi. Narxlar haftasiga 20% o'zgaradi va egalari qancha xarajat qilayotganini ko'ra olmaydi…",
  },
  product: {
    title: 'Mahsulot',
    question: 'Nima qurdingiz va u muammoni qanday hal qiladi?',
    hint: "Bugungi kunda haqiqatda mavjud narsani yozing — reja emas. Mijozlar undan qanday foydalanadi va siz qanday pul topasiz?",
    placeholder:
      "Masalan: Restoranlarni tekshirilgan ulgurji yetkazib beruvchilar bilan bog'laydigan buyurtma ilovasi. 22:00 gacha bitta buyurtma, 07:00 gacha yetkazma, bitta hisob-faktura. Biz 6% olamiz…",
  },
  market: {
    title: 'Bozor',
    question: 'Imkoniyat qanchalik katta?',
    hint: "Bozorni halol baholang, iloji bo'lsa quyidan yuqoriga hisoblab. Bu pul uchun yana kim raqobatlashadi — \"hech narsa qilmaslik\" ham shu jumlaga kiradi?",
    placeholder:
      "Masalan: Toshkentda 12 000 umumiy ovqatlanish korxonasi xaridga oyiga $8–15 ming sarflaydi — yiliga qariyb $600M lik oqim…",
  },
  traction: {
    title: 'Natijalar',
    question: 'Bu ishlayotganiga qanday isbotingiz bor?',
    hint: "Sifatlar emas, raqamlar: mijozlar, daromad, o'sish sur'ati, mijozlarning qolishi. Hali daromad bo'lmasa, ochiq ayting — halollik bo'rttirishdan yaxshiroq o'qiladi.",
    placeholder:
      "Masalan: 9 oydan beri ishlaymiz. 214 restoran har hafta buyurtma beradi. O'tgan oy GMV $412 000, oyiga 18% o'sish. Churn 3% dan past…",
  },
  team: {
    title: 'Jamoa',
    question: 'Buni kim qurmoqda va nega aynan siz?',
    hint: "Asoschilar, ularning tegishli tajribasi, kim to'liq stavkada ishlashi va ulushlar qanday taqsimlangani. Investorlar g'oyadan ko'ra jamoaga pul beradi.",
    placeholder:
      "Masalan: CEO besh yil kafelar tarmog'ining ta'minotini boshqargan; CTO Uzumda logistika marshrutlashini qurgan. Ikkalasi to'liq stavkada, birgalikda 82% ulush…",
  },
  ask: {
    title: "So'rov",
    question: 'Qancha jalb qilyapsiz va bu pul nimaga sarflanadi?',
    hint: "Summa, ulush va bu mablag' nimaga erishtirishi. Allaqachon kelishilgan investitsiyalarni ham ayting.",
    placeholder:
      "Masalan: Yana ikki shaharga kengayish va ikki savdo rahbarini yollash uchun 12% evaziga $500 000 seed jalb qilmoqdamiz. $180 000 allaqachon kelishilgan…",
  },
}
