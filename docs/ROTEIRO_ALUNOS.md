# Laboratório: testando o Estoque Inteligente na AWS

Acesse no navegador: **http://______________** (IP informado pelo instrutor)

O sistema que você vai usar está rodando de verdade na nuvem da AWS. Cada ação sua passa
por vários serviços. Em cada atividade, anote **qual serviço da AWS foi usado**.

---

### Atividade 1: Onde estou? (EC2 + VPC)

1. Abra a aba **Arquitetura AWS**.
2. Anote: ID da instância EC2, tipo da instância e **zona de disponibilidade (AZ)**.
3. Por que o IP que você digitou no navegador é diferente do "IP privado" mostrado na tela?

### Atividade 2: Cadastro (S3)

1. Na tela **Cadastro**, cadastre um produto com o seu nome no nome do produto (ex.: "Caneca do João"). Anote o **código (SKU) que o sistema gerou**
   Use quantidade 20 e estoque mínimo 5.
2. Peça para um colega procurar o seu item na busca. Ele aparece? Por quê?

### Atividade 3: Fotos (S3)

1. Na tela **Cadastro**, crie um produto com foto, ou abra um produto e clique em **Enviar foto**.
2. Clique com o botão direito na foto → *Copiar endereço da imagem*. O endereço é do **site**, não do S3.
   Por que o sistema não deixa o navegador acessar o bucket diretamente? (dica: bucket privado, credenciais)
3. Quando o instrutor derrubar o S3: o que acontece com as fotos? E com o resto do sistema?

### Atividade 4: Movimentações

1. Registre uma **saída** de 16 unidades do seu item.
2. O que mudou no card do item? E no **Dashboard**?
3. Tente registrar uma saída maior que o estoque. O que acontece?

### Atividade 5: Previsão de demanda

1. Abra o item **SSD NVMe 1TB Samsung** e clique em **Calcular previsão**.
2. Anote: previsão para 7 dias e em quantos dias o estoque acaba.
3. Compare com o **Cabo HDMI 2m**. Qual precisa de reposição antes?

### Atividade 6: Assistente de IA (Bedrock + Lambda)

Abra o botão **Assistente IA** no canto inferior direito (ele aparece em todas as telas).

Teste (uma por vez):

- "Quais itens estão com estoque baixo?"
- "Qual o valor total do estoque?"
- "Quantas webcams temos e quanto custa cada uma?"
- "Em quantos dias o mouse vai acabar?"
- "Registre a entrada de 30 mouses que chegaram do fornecedor"
- Agora vá à tela **Produtos**: o estoque do mouse mudou?
- Invente uma pergunta sua!

Responda:
1. O assistente acessou o S3 **diretamente**? Quem fez isso por ele?
2. Por que a Lambda consegue falar com a EC2 mesmo estando em uma sub-rede **privada**, sem internet?
3. Faça uma pergunta fora do assunto (ex.: "qual a capital da França?"). Como o agente se comporta?

### Atividade 7: Para pensar (Cloud Practitioner)

1. Classifique cada serviço como **IaaS, PaaS ou SaaS/serverless**: EC2, S3, Lambda, Bedrock.
2. Pelo **modelo de responsabilidade compartilhada**: quem atualiza o sistema operacional da EC2? E a durabilidade dos dados no S3? E o runtime da Lambda?
3. O sistema está em **uma** EC2 só, e os dados ficam num **único** bucket S3. O que acontece se a AZ da EC2 tiver problema? E se o bucket ficasse inacessível?
   Que serviços você usaria para tornar a EC2 altamente disponível? (dica: ELB, Auto Scaling)
4. Quais serviços cobram por hora ligados e quais cobram só quando são usados?
5. Por que este laboratório não usa um banco de dados gerenciado (como o Aurora)? Que vantagens um banco relacional traria, e que complexidade ele adicionaria ao deploy?
