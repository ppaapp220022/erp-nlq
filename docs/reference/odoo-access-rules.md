# Odoo 접근 규칙 조사 (M1)

> 근거 데이터는 `./scripts/odoo-shell.sh scripts/odoo_access_report.py`의 출력이다. 대상은 Odoo 19.0(20261102 빌드)과 스냅숏 `erp-20261103`의 데모 데이터에 시드를 적용한 상태다.
> Odoo나 데이터가 바뀌면 다시 돌려 이 문서와 비교한다.

## Odoo가 권한을 합치는 방식

1. **모델 접근(ACL, `ir.model.access`)**: 그 모델을 읽을 수 있는지를 먼저 본다. 읽을 수 없으면 거기서 끝이다.
2. **Record Rule(`ir.rule`)**: 읽을 수 있는 행을 정한다.
   - **전역 규칙**(그룹 없음)끼리는 **AND**로 합친다. 거의 모든 모델에 회사 규칙이 하나씩 있다.
   - **그룹 규칙**은 사용자가 속한 그룹의 규칙끼리 **OR**로 합친다.
   - 최종 범위는 `전역 규칙 AND (그룹 규칙1 OR 그룹 규칙2 ...)`이다.

`ir.rule._compute_domain()`이 사용자별로 계산한 실제 도메인으로 확인했다. 둘째 줄은 송장 예시다.
`sale.order`: `company_id in [3,2,1] AND user_id in [uid, False]`
`account.move`: `company_id in [3,2,1] AND invoice_user_id in [uid, False] AND move_type in ('out_invoice','out_refund')`

## 허용 테이블 (13개 + `res_users` 일부 열)

[db/readonly_role.sql](../../db/readonly_role.sql)에 반영했다. 고른 기준은 계획의 ERP 업무 질문 예시 7개에 답할 수 있는 최소 집합이다.

| 영역 | 테이블 | 쓰는 질문 | 주의 |
|---|---|---|---|
| 판매 | `sale_order` | 거래처별 매출, 미출고 확정 주문(`delivery_status`) | |
| 판매 | `sale_order_line` | 품목별 판매량 | 권한 규칙이 주문과 다르다(아래) |
| 구매 | `purchase_order` | 입고 안 된 구매(`receipt_status`) | |
| 구매 | `purchase_order_line` | 품목별 미입고 수량(`qty_received`) | |
| 재고 | `stock_picking` | 출고·입고 건 | |
| 재고 | `stock_quant` | 현재 재고 | 창고 밖 위치에도 있다. internal 18건, customer 4건, inventory 21건 |
| 재고 | `stock_location` | `usage = 'internal'` 거르기 | `stock_quant`를 쓰려면 반드시 필요하다 |
| 재고 | `stock_warehouse_orderpoint` | 안전 재고(`product_min_qty`) | 데모에 3건뿐 |
| 회계 | `account_move` | 미수 송장(`invoice_date_due`, `amount_residual`), 부가세 제외 매출, 환불 | `move_type`과 `state`를 함께 봐야 한다 |
| 공통 | `res_partner` | 거래처 이름 | 회사와 담당자가 한 테이블에 섞여 있다 |
| 공통 | `res_company` | 회사 이름 | 데모에 회사가 3개 있다 |
| 공통 | `product_product`, `product_template` | 품목 이름 | `product_template.name`은 jsonb(번역 필드)다 |
| 보조 | `res_users` (`id, partner_id, company_id, active`만) | 담당 영업 사원 이름 연결 | 비밀번호 열은 주지 않는다 |

뺀 테이블과 이유는 다음과 같다.
- `stock_move`: 질문 예시는 `stock_picking`과 주문의 `delivery_status`·`receipt_status`로 충분하다.
- `account_move_line`: 품목별 송장 매출 같은 질문이 평가 문항에 들어가면 연다.
- `res_currency`, `product_category`, `uom_uom`: 예시 질문에 필요 없다.

## 테이블별 읽기 규칙

포털·공개 사용자 규칙은 이 프로젝트의 역할이 아니라 뺐다.

| 모델 | 전역(AND) | 그룹 규칙(OR) |
|---|---|---|
| `sale.order` | 회사 | 영업 사원: 내 주문 + 담당자 없음 · 전체 보기 그룹: 전부 |
| `sale.order.line` | 회사 | 영업 사원: `salesman_id` 기준 내 것 + 없음 · 전체 보기 그룹: 전부 · **재고 사용자: 전부** |
| `purchase.order(.line)` | 회사 | 없음 |
| `stock.picking`, `stock.warehouse.orderpoint` | 회사 | 없음 |
| `stock.quant`, `stock.location` | 회사 또는 회사 없음 | 없음 |
| `account.move` | 회사 | 영업 사원: 고객 송장·환불 중 내 것 + 없음 · 구매 사용자: 공급사 송장 · 회계 그룹: 전부 |
| `res.partner` | 내부 사용자 파트너, 또는 회사 계층 안, 또는 회사 없음 | 없음 |
| `product.template` | 회사 계층 안, 또는 회사 없음 | 없음 |
| `res.company` | | 내부 사용자: 속한 회사 · ERP 관리자: 전부 |

근거 XML ID는 다음과 같다. 소스는 컨테이너 안 `/usr/lib/python3/dist-packages/odoo/addons/<모듈>/security/`에 있다.
- `sale.sale_order_personal_rule`
- `sale.sale_order_line_personal_rule`
- `sale_stock.sale_order_line_rule_stock_user`
- `sale.account_invoice_rule_see_personal`
- `purchase.purchase_user_account_move_rule`
- 그 밖에 모델마다 `*_comp_rule`이 있다.

## 발견한 것

1. **행 범위에는 항상 회사 조건이 붙는다.** 데모 영업 사원은 회사 3개에 속해 있다. 자세한 경위는 드라이브 troubleshooting `2026-11-03-invoice-count-mismatch-multi-company.md`에 있다.
2. **데모 영업 사원은 재고 사용자이기도 하다.** 그룹 규칙은 OR로 합쳐지므로, `sale.order.line`의 "재고 사용자: 전부" 규칙이 영업 사원 규칙을 덮는다. 그래서 같은 사용자에게 **주문은 8건만 보이는데 주문 라인은 50건 전부** 보인다. 같은 이유로 구매 주문(11건), 출고(49건)도 전부 읽을 수 있다. Odoo의 실제 동작이 이렇고, 권한 일치를 목표로 하면 guard도 이렇게 해야 한다.
3. **영업 사원은 고객 송장만 본다.** 공급사 송장은 구매 사용자 그룹이 있어야 보인다.
4. **거래처와 품목은 회사 범위 안에서 모두 보인다.** 영업 사원도 44개 거래처와 47개 품목을 모두 읽는다.

## 결정: 역할 분리 (ADR 0002)

위 발견 2 때문에 시드에서 영업 사원의 재고 그룹을 빼고 재고 담당(`stock.choi`)을 따로 만들었다. 역할별 범위는 [ADR 0002](../adr/0002-separate-sales-and-stock-roles.md)에 있다. 조사 스크립트는 이제 `sales.kim`, `stock.choi`, `admin` 세 명을 출력한다.

분리 후 알게 된 것은 두 가지다.
- 영업 사원은 재고 그룹이 없어도 출고·재고 문서를 읽는다(판매-재고 연동 모듈의 ACL). 행 범위는 회사 조건뿐이다.
- 재고 담당은 판매 주문을 전부 본다. 재고 담당의 그룹 중 `sale.order`에 그룹 규칙이 걸린 것이 없어서 전역 규칙(회사)만 적용되기 때문이다.
